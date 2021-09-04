from collections import defaultdict
from datetime import date
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django_permanent.models import PermanentModel

from caravans.models import SKUCategory

from orders.models import Order
from caravans.models import Series
from dealerships.models import Dealership
from production.models import Build

# from caravans.models import SKU

class Capacity(PermanentModel, models.Model):
    """
    Manufacturing capacity for a given day
    """

    SCHEDULE_I = 1
    SCHEDULE_II = 2

    SCHEDULE_UNIT = (
        (SCHEDULE_I, 'Caravans'),
        (SCHEDULE_II, 'Pop-Top/Campers'),
    )

    CAPACITY_TYPE_CLOSED = 0
    CAPACITY_TYPE_OPEN = 1
    CAPACITY_TYPE_HOLIDAY = 2
    CAPACITY_TYPE_CHOICES = (
        (CAPACITY_TYPE_CLOSED,  'Closed'),
        (CAPACITY_TYPE_OPEN,    'Open'),
        (CAPACITY_TYPE_HOLIDAY, 'Holiday'),
    )

    day = models.DateField("Day")
    production_unit = models.IntegerField(choices = SCHEDULE_UNIT)
    capacity = models.IntegerField("Capacity")

    # 25/05/2016: The type and holiday name are not used anymore
    type = models.IntegerField(choices=CAPACITY_TYPE_CHOICES, default=CAPACITY_TYPE_CLOSED)
    holiday_name = models.CharField("Holiday", max_length=255, blank=True)

    fixtures_autodump = ['dev']

    class Meta:
        unique_together = ('day', 'production_unit',)
        db_table = 'schedule_capacity'
        verbose_name = 'Production Capacity'
        verbose_name_plural = 'Production Capacities'

    def save(self, *args, **kwargs):

        # 25/05/2016: The type is not used anymore and will be set to OPEN if capacity > 0 and to CLOSED otherwise.
        if self.capacity > 0:
            self.type = Capacity.CAPACITY_TYPE_OPEN
        else:
            self.type = Capacity.CAPACITY_TYPE_CLOSED

        self.holiday_name = ''

        # Old logic for historical purposes:
        # if self.type != Capacity.CAPACITY_TYPE_OPEN:
        #     self.capacity = 0
        # if self.type != Capacity.CAPACITY_TYPE_HOLIDAY:
        #     self.holiday_name = ''

        return super(Capacity, self).save(*args, **kwargs)

    @staticmethod
    def get_capacities_dict(date_from, date_to, include_utilization):
        """
        Get a dictionary of capacities for a given date range [date_from, date_to)
        If there are no entries in the DB, will create a placeholder closed Capacity entry
        :param date_from: first date (inclusive)
        :param date_to: last date (not inclusive)
        :param include_utilization: whether to include a utilization count
        :return: defaultdict
        """
        default_capacity = Capacity(capacity=0, type=Capacity.CAPACITY_TYPE_CLOSED)
        capacities = Capacity.objects \
            .filter(day__gte=date_from, day__lte=date_to)
        capacities = ((capacity.day, capacity) for capacity in capacities)
        capacities = defaultdict(lambda: default_capacity, capacities)

        if include_utilization:
            for capacity in capacities.values():
                capacity.utilization = 0
            default_capacity.utilization = 0
            for row in Build.objects \
                    .filter(build_date__gte=date_from, build_date__lte=date_to) \
                    .values('build_date') \
                    .annotate(count=models.Count('pk')):
                build_date = row['build_date']
                if build_date not in capacities:
                    capacities[build_date] = Capacity(capacity=0, type=Capacity.CAPACITY_TYPE_CLOSED)
                capacities[build_date].utilization = row['count']

        return capacities

    @staticmethod
    def get_working_day_relative(date, days_offset, capacities):
        """
        Increment/decrement a date by a number of working days
        :param date: date to start counting from
        :param days_offset: number of working days to move forward/backwards by.
        :param capacities: dict of Capacity indexed by date (see get_capacities_dict())
        :return: None if found. If days_offset == 0 and that day is not open, is undefined what will be returned
        """
        no_capacity = Capacity(capacity=0)
        date_delta = timedelta(days=cmp(days_offset, 0))
        days_remaining = abs(days_offset)
        search_limit = settings.SCHEDULE_WORKING_SEARCH_WINDOW
        # we use search_limit to prevent infinite loops
        while search_limit >= 0 and days_remaining > 0:
            date += date_delta
            if capacities.get(date, no_capacity).capacity > 0:
                days_remaining -= 1
                search_limit = settings.SCHEDULE_WORKING_SEARCH_WINDOW
            else:
                search_limit -= 1
        ret = date if days_remaining == 0 else None
        return date if days_remaining == 0 else None


def generate_test_capacity_data():
    # Generate SQL for insertion into capacity table
    import random
    random.seed(6)
    start = date(year=2015,month=12,day=1)
    for x in range(365):
        d = start + timedelta(days=x)
        type = Capacity.CAPACITY_TYPE_CLOSED
        capacity = 0
        holiday_name = ''
        if d.weekday() < 5:
            if random.randint(0, 4) == 0:
                type = Capacity.CAPACITY_TYPE_HOLIDAY
                holiday_name = 'Holiday %d' % x
            else:
                type = Capacity.CAPACITY_TYPE_OPEN
                holiday_name = ''
                capacity = random.randint(1, 2)

        # if random.randint(0, 2) > 0:
        #     # occasionally just don't fill anything in at all
        #     print "INSERT INTO schedule_capacity (day, type, holiday_name, capacity) VALUES ('%s', %d, '%s', %d);" % (
        #         d.isoformat(),
        #         type,
        #         holiday_name,
        #         capacity,
        #     )


class MonthPlanning(models.Model):
    SCHEDULE_I = 1
    SCHEDULE_II = 2

    SCHEDULE_UNIT = (
        (SCHEDULE_I, 'Caravans'),
        (SCHEDULE_II, 'Pop-Top/Campers'),
    )

    MONTH_PLANNING_DEFAULT_LENGTH = 24  # months

    DEFAULT_WEEK_OFFSET_FOR_FINALISATION1 = 19
    DEFAULT_WEEK_OFFSET_FOR_FINALISATION2 = 17
    DEFAULT_WEEK_OFFSET_FOR_SIGNOFF = 11
    DEFAULT_WEEK_OFFSET_FOR_SIGNOFF2 = 9
    DEFAULT_WEEK_OFFSET_FOR_DRAFT_COMPLETION = 13

    production_unit = models.IntegerField(choices = SCHEDULE_UNIT)
    production_month = models.DateField(help_text="The first day of the month represented by this model.")
    production_start_date = models.DateField(null=True, blank=True, help_text="The date when the production actually starts for this month.")
    sign_off_reminder = models.DateField()
    sign_off_reminder_sent = models.BooleanField(default=False)
    draft_completion = models.DateField()
    closed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('production_month', 'production_unit',)

    fixtures_autodump = ['dev']

    def next(self):
        return MonthPlanning.objects.get_or_create(
            production_month=self.production_month + relativedelta(months=1), production_unit=self.production_unit
        )[0]

    def has_available_spots(self):
        if not self.production_start_date or not self.next().production_start_date or self.closed:
            return False
        return self.get_capacity(self.production_unit) > self.get_total_order_count()

    def get_capacity(self, production_unit):

        """
        Calculates the total build capacity for the given planning month.

        Returns: The total number of builds that can be assigned to the given month.
        """
        if not self.production_start_date or not self.next().production_start_date:
            raise ImproperlyConfigured('Could not determine capacity for {}. Please check configuration in Schedule Planner.'.format(self))

        # print(' Current Date :', self.production_start_date , ' : ',  self.production_month)
        
        # print('Next Date :', self.next().production_start_date, ' : ',  self.next().production_month )

        return sum(
            Capacity.objects.filter(
                production_unit=production_unit,
                day__gte=self.production_month,
                day__lt=self.next().production_month,
                capacity__gt=0
            ).values_list('capacity', flat=True)
        )

    def get_total_order_count(self):
        """
        Calculates the total number of orders for the given planning month.

        Returns: The total number of orders assigned to the given month
        """
        return Order.objects.filter(
            build__build_order__production_month=self.production_month,
            build__build_order__production_unit = self.production_unit,
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
        ).count()

    def save(self, *args, **kwargs):
        self.production_month = self.production_month.replace(day=1)

        if self.sign_off_reminder is None:
            self.sign_off_reminder = MonthPlanning._get_last_business_day(
                self.production_month - timedelta(MonthPlanning.DEFAULT_WEEK_OFFSET_FOR_SIGNOFF * 7)
            )

        if self.draft_completion is None:
            self.draft_completion = MonthPlanning._get_last_business_day(
                self.production_month - timedelta(MonthPlanning.DEFAULT_WEEK_OFFSET_FOR_DRAFT_COMPLETION*7)
            )

        super(MonthPlanning, self).save(*args, **kwargs)

    @staticmethod
    def get_for_date(date, production_unit):
        """
        Returns the MonthPlanning object corresponding to the given date, or None if no MonthPlanning is defined for this date
        """
        return MonthPlanning.objects.filter(production_start_date__lte=date, production_unit=production_unit).order_by('-production_month').first()

    @staticmethod
    def _get_last_business_day(date):
        if date.weekday() > 4: # Saturday or Sunday
            return date - timedelta(date.weekday() - 4) # return last Friday
        return date

    def __str__(self):
        return self.production_month.strftime(settings.FORMAT_DATE_MONTH)


class DealerMonthPlanning(models.Model):
    SCHEDULE_I = 1
    SCHEDULE_II = 2

    SCHEDULE_UNIT = (
        (SCHEDULE_I, 'Caravans'),
        (SCHEDULE_II, 'Pop-Top/Campers'),
    )

    MONTH_PLANNING_DEFAULT_LENGTH = 24  # months

    

    dealership_id = models.IntegerField()
    production_month = models.DateField(help_text="The first day of the month represented by this model.")
    capacity_allotted = models.IntegerField(default=0)
    production_unit = models.IntegerField(default=1)

    class Meta:
        unique_together = ('production_month', 'production_unit','dealership_id')

    fixtures_autodump = ['dev']

    def next(self):
        return MonthPlanning.objects.get_or_create(
            production_month=self.production_month + relativedelta(months=1), production_unit=self.production_unit
        )[0]

    def has_available_spots(self):
        if not self.production_start_date or not self.next().production_start_date or self.closed:
            return False
        return self.get_capacity(self.production_unit) > self.get_total_order_count()

    def get_capacity(self, production_unit):

        """
        Calculates the total build capacity for the given planning month.

        Returns: The total number of builds that can be assigned to the given month.
        """
        if not self.production_start_date or not self.next().production_start_date:
            raise ImproperlyConfigured('Could not determine capacity for {}. Please check configuration in Schedule Planner.'.format(self))

        # print(' Current Date :', self.production_start_date , ' : ',  self.production_month)
        
        # print('Next Date :', self.next().production_start_date, ' : ',  self.next().production_month )

        return sum(
            Capacity.objects.filter(
                production_unit=production_unit,
                day__gte=self.production_month,
                day__lt=self.next().production_month,
                capacity__gt=0
            ).values_list('capacity', flat=True)
        )

    def get_total_order_count(self):
        """
        Calculates the total number of orders for the given planning month.

        Returns: The total number of orders assigned to the given month
        """
        return Order.objects.filter(
            build__build_order__production_month=self.production_month,
            build__build_order__production_unit = self.production_unit,
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
        ).count()

    # def save(self, *args, **kwargs):
    #     self.production_month = self.production_month.replace(day=1)

    #     # if self.sign_off_reminder is None:
    #     #     self.sign_off_reminder = MonthPlanning._get_last_business_day(
    #     #         self.production_month - timedelta(MonthPlanning.DEFAULT_WEEK_OFFSET_FOR_SIGNOFF * 7)
    #     #     )

    #     # if self.draft_completion is None:
    #     #     self.draft_completion = MonthPlanning._get_last_business_day(
    #     #         self.production_month - timedelta(MonthPlanning.DEFAULT_WEEK_OFFSET_FOR_DRAFT_COMPLETION*7)
    #     #     )

    #     super(DealerMonthPlanning, self).save(*args, **kwargs)

    @staticmethod
    def get_for_date(date, production_unit):
        """
        Returns the MonthPlanning object corresponding to the given date, or None if no MonthPlanning is defined for this date
        """
        return MonthPlanning.objects.filter(production_start_date__lte=date, production_unit=production_unit).order_by('-production_month').first()

    @staticmethod
    def _get_last_business_day(date):
        if date.weekday() > 4: # Saturday or Sunday
            return date - timedelta(date.weekday() - 4) # return last Friday
        return date

    def __str__(self):
        return self.production_month.strftime(settings.FORMAT_DATE_MONTH)

class ContractorScheduleExport(models.Model):

    name = models.CharField(max_length=100)
    production_date_offset = models.IntegerField(default=0)

    fixtures_autodump = ['dev']

    class Meta(object):
        ordering = ('name',)

    def __str__(self):
        return self.name


class ContractorScheduleExportColumn(models.Model):

    # The value corresponds to the actual field name in caravans.models.SKU
    DEFAULT_FIELD = 'description'
    DESCRIPTION_FIELD1 = 'contractor_description1'
    DESCRIPTION_FIELD2 = 'contractor_description2'
    DESCRIPTION_FIELD3 = 'contractor_description3'
    DESCRIPTION_FIELD4 = 'contractor_description4'
    DESCRIPTION_FIELD5 = 'contractor_description5'

    DESCRIPTION_FIELDS = (
        (DEFAULT_FIELD, 'Use item description'),
        (DESCRIPTION_FIELD1, 'Contractor desc 1'),
        (DESCRIPTION_FIELD2, 'Contractor desc 2'),
        (DESCRIPTION_FIELD3, 'Contractor desc 3'),
        (DESCRIPTION_FIELD4, 'Contractor desc 4'),
        (DESCRIPTION_FIELD5, 'Contractor desc 5'),
    )

    name = models.CharField(max_length=100)
    export = models.ForeignKey(ContractorScheduleExport, on_delete=models.DO_NOTHING)
    sequence = models.IntegerField()
    department = models.ForeignKey(SKUCategory, on_delete=models.DO_NOTHING)
    # sku = models.ForeignKey(SKU, null=True, blank=True, on_delete=models.DO_NOTHING)
    # code = models.ForeignKey(SKU, on_delete=models.DO_NOTHING,default=False)
    contractor_description_field = models.CharField(max_length=50, choices=DESCRIPTION_FIELDS, default=DEFAULT_FIELD)

    fixtures_autodump = ['dev']

    class Meta(object):
        ordering = ('sequence', 'name',)

    def __str__(self):
        return self.name + ' (' + str(self.export) + ')'


class OrderTransport(PermanentModel, models.Model):
    id = models.AutoField(primary_key=True)
    order = models.OneToOneField(Order, on_delete=models.PROTECT, null=True)    #modified

    actual_production_date = models.DateField(null=True, blank=True)
    actual_production_comments = models.TextField(null=True)    

    # planned_watertest_date = models.DateField(null=True, blank=True)
    watertest_date = models.DateField(null=True, blank=True)
    watertest_comments = models.TextField(null=True)

    qc_comments = models.TextField(null=True)
    
    dispatch_comments = models.TextField(null=True)
    
    final_qc_date = models.DateField(null=True, blank=True)
    final_qc_comments = models.TextField(null=True)

    chassis_section = models.DateField(null=True, blank=True)
    chassis_section_comments = models.TextField(null=True)

    building = models.DateField(null=True, blank=True)
    building_comments = models.TextField(null=True)

    prewire_section = models.DateField(null=True, blank=True)
    prewire_comments = models.TextField(null=True)

    plumbing_date = models.DateField(null=True, blank=True)
    plumbing_comments = models.TextField(null=True)

    aluminium = models.DateField(null=True, blank=True)
    aluminium_comments = models.TextField(null=True)

    finishing = models.DateField(null=True, blank=True)
    finishing_comments = models.TextField(null=True)

    hold_caravans = models.BooleanField(default=False)

    weigh_bridge_date = models.DateField(null=True, blank=True)
    weigh_bridge_comments = models.TextField(null=True)

    detailing_date = models.DateField(null=True, blank=True)
    detailing_comments = models.TextField(null=True)
    
    email_sent = models.DateField(null=True, blank=True)
    
    collection_date = models.DateField(null=True, blank=True)
    collection_comments = models.TextField(null=True)
    
    senior_designer_verfied_date = models.DateField(null=True, blank=True)

    purchase_order_raised_date = models.DateField(null=True, blank=True)
    
    

    fixtures_autodump = ['dev']

    def __str__(self):
        return '%d for %s' % (self.id, self.order)

    class Meta:
        db_table = 'orders_transport'
        verbose_name = 'Order OrderTransport Details'
        verbose_name_plural = 'Order OrderTransport Details'


# class ProductionUnit(PermanentModel, models.Model):
#     id = models.AutoField(primary_key=True)
#     order = models.OneToOneField(Order, on_delete=models.PROTECT)
#     series = models.ForeignKey(Series, on_delete=models.PROTECT)
#     production_unit = models.IntegerField(default=1)

#     fixtures_autodump = ['dev']

#     def __str__(self):
#         return '%s for %s' % (self.order, self.production_unit)

#     class Meta:
#         db_table = 'schedule_unit'
#         verbose_name = 'Production Unit Details'
#         verbose_name_plural = 'Production Unit Details'