

from datetime import timedelta
from datetime import date

from datetime import datetime
from datetime import date
from datetime import timedelta

from django.shortcuts import render

import time

from wkhtmltopdf.views import PDFTemplateResponse



from dateutil import parser

import itertools

from django.conf import settings
from django.http.response import HttpResponseBadRequest
from django.utils.dateparse import parse_date
from django.views.generic import View
from rules.contrib.views import PermissionRequiredMixin

from caravans.models import SeriesSKU
from caravans.models import Series

from newage.utils import ExportCSVMixin
from newage.utils import PrintableMixin

from orders.models import Order
from orders.models import OrderDocument
from orders.models import OrderSKU
from orders.models import SpecialFeature

from caravans.models import SeriesSKU
from caravans.models import SKUCategory
from caravans.models import Supplier

from schedule.models import Capacity
from schedule.models import OrderTransport
from schedule.models import ContractorScheduleExport
from schedule.models import MonthPlanning
from production.models import Build
from dealerships.models import Dealership

from caravans.models import SKU

# import unicodecsv as csv

def get_status(order):
    if order.order_cancelled is not None:
        return 'Cancelled'

    if order.get_finalization_status() != Order.STATUS_APPROVED:
        return 'Pending'

    customer_approval_status = order.get_customer_plan_status()

    if customer_approval_status in (Order.STATUS_NONE, Order.STATUS_REJECTED):
        return 'Drafting'

    if customer_approval_status == Order.STATUS_PENDING:
        return 'Signoff'

    if customer_approval_status == Order.STATUS_APPROVED:
        return 'Ready'

    return 'Unknown'

class ScheduleCSVView(ExportCSVMixin, PermissionRequiredMixin, View):
    permission_required = 'schedule.export_schedule'

    def get_file_name(self):
        return 'Schedule Export'

    def get_complete_file_name(self):
        return '{0} {1}-{2}'.format(self.get_file_name(),
                                    self.date_from.strftime(settings.FORMAT_DATE_MONTH),
                                    self.date_to.strftime(settings.FORMAT_DATE_MONTH))

    def get_headers(self, table=None):
        headers = ['Schedule Month',
                   'Schedule #',
                   'Production Date',
                   'Status',
                   'Order #',
                   'Chassis #',
                   'Model / Series',
                   'Show Name',
                   'Dealership Name',
                   'Customer Name',
                   'Drafter Name',
                   'VIN No.',
                   'Comments',
                   'Production Status']
        return headers

    def get_rows(self, table=None):

        rows = [
            [
                order.build.build_order.production_month.strftime(settings.FORMAT_DATE_MONTH),
                str(order.build.build_order.order_number),
                order.build.build_date.strftime(settings.FORMAT_DATE) if order.build.build_date else '',
                get_status(order),
                str(order.id),
                order.chassis,
                order.get_series_code(),
                order.show.name if order.show else '',
                order.dealership.name,
                order.customer.get_full_name() if order.customer else 'STOCK',
                order.build.drafter.get_full_name() if order.build.drafter else '',
                order.build.vin_number,
                order.scheduling_comments,
                get_status_of_order(order.id),
            ]
            for order in self.orders
            ]

        return rows

    def get(self, request, unit_id, date_from, date_to):
        self.date_from = parse_date(date_from + '-01')
        self.date_to = parse_date(date_to + '-01')
        self.production_unit = unit_id

        if date_from > date_to:
            return HttpResponseBadRequest("The start date is greater than the end date.")

        self.orders = Order \
            .objects \
            .filter(
            build__build_order__production_month__gte=self.date_from,
            build__build_order__production_month__lte=self.date_to,
            build__build_order__production_unit=self.production_unit,
            ) \
            .order_by('build__build_order__production_month', 'build__build_order__order_number') \
            .select_related(
            'build__build_order',
            'orderseries',
            'orderseries__series',
            'orderseries__series__model',
            'show',
            'dealership',
            'customer',
            'build__drafter',
        )
        return self.write_csv()


# global_orders=[]

class SchedulePDFView(PrintableMixin, PermissionRequiredMixin, View):
    global_orders=[]
    permission_required = 'schedule.export_schedule'

    template_name = 'orders/printable/specs_bulk_pdf.html'

    def get(self, request, unit_id, date_from):
        
        self.date_from = parse_date(date_from + '-01')
        self.production_unit = unit_id
        self.date_to = parse_date(date_from + '-01')

        my_orders = Order \
            .objects \
            .filter(
            build__build_order__production_month__gte=self.date_from,
            build__build_order__production_month__lte=self.date_to,
            build__build_order__production_unit=self.production_unit,
            ) \
            .order_by('build__build_order__production_month', 'build__build_order__order_number') \
            .select_related(
            'build__build_order',
        )

        orders1=[]
        import threading
        t = threading.Thread(target=self.background_process(self,  my_orders), args=(my_orders), kwargs={})
        t.setDaemon(True)
        t.start()
        
        # orders1 = background_process(my_orders)
        # i=0
        # for myord in my_orders: 

        #     order = Order.objects.get(id=myord.id)

        #     plans_completed = order.get_finalization_status() == Order.STATUS_APPROVED

        #     categories = []
        #     top_level_categories_by_id = {}

        #     for skucategory in SKUCategory.top().skucategory_set.all().order_by('print_order'):
        #         category = {
        #             'name': skucategory.name,
        #             'print_order': skucategory.print_order,
        #             'features': [],
        #             'extras': [],
        #             'special_features': [],
        #         }

        #         categories.append(category)
        #         top_level_categories_by_id[skucategory.id] = category

        #     special_feature_overrides = []

        #     for ordersku in order.ordersku_set.all().prefetch_related('sku', 'sku__sku_category'):
        #         # If a SeriesSKU doesn't exist, we show it in red.
        #         try:
        #             seriessku = SeriesSKU.objects.get(series=order.orderseries.series, sku=ordersku.sku)
        #         except SeriesSKU.DoesNotExist:
        #             seriessku = None

        #         if seriessku and not seriessku.is_visible_on_spec_sheet:
        #             continue

        #         cat = ordersku.sku.sku_category
        #         while cat.id not in top_level_categories_by_id:
        #             cat = cat.parent

        #         key = 'features'

        #         item = {
        #             'red': not seriessku or ordersku.base_availability_type != SeriesSKU.AVAILABILITY_STANDARD,
        #             'description': ordersku.sku.name,
        #         }

        #         if plans_completed:
        #             # If a special feature is defined for this item, use the special feature description
        #             try:
        #                 special_feature = order.specialfeature_set.get(sku_category=ordersku.sku.sku_category)
        #                 special_feature_overrides.append(special_feature.id)
        #                 item = {
        #                     'red': True,
        #                     'description': special_feature.factory_description,
        #                 }
        #             except SpecialFeature.DoesNotExist:
        #                 pass

        #         if ordersku.base_availability_type == SeriesSKU.AVAILABILITY_OPTION:
        #             key = 'extras'
        #         elif ordersku.base_availability_type == SeriesSKU.AVAILABILITY_SELECTION:
        #             item['department'] = ordersku.sku.sku_category.name

        #         top_level_categories_by_id[cat.id][key].append(item)

        #     # Add any departments missing selections if order is not finalised
        #     if order.get_finalization_status() not in (Order.STATUS_APPROVED, Order.STATUS_PENDING):
        #         departments = SKUCategory.objects.filter(parent__parent=SKUCategory.top())
        #         availability_types = [
        #             SeriesSKU.AVAILABILITY_STANDARD,
        #             SeriesSKU.AVAILABILITY_SELECTION,
        #             SeriesSKU.AVAILABILITY_UPGRADE
        #         ]
        #         selections = set([osku.sku.sku_category.id for osku in order.ordersku_set.filter(base_availability_type__in=availability_types)])
        #         departments_missing = set()
        #         for d in departments:
        #             requires_selections = SeriesSKU.objects.filter(
        #                 is_visible_on_spec_sheet=True,
        #                 sku__sku_category=d,
        #                 series=order.orderseries.series,
        #                 availability_type__in=availability_types).count()
        #             if requires_selections and d.id not in selections and d.id not in departments_missing:
        #                 departments_missing.add(d.id)
        #                 top_level_categories_by_id[d.parent.id]['features'].append({
        #                     'missing_selections': True,
        #                     'description': d.name,
        #                 })

        #     if plans_completed:
        #         for special_feature in order.specialfeature_set.filter(sku_category__isnull=False).exclude(id__in=special_feature_overrides).prefetch_related('sku_category'):
        #             cat = special_feature.sku_category
        #             while cat.id not in top_level_categories_by_id:
        #                 cat = cat.parent

        #             top_level_categories_by_id[cat.id]['special_features'].append(special_feature.factory_description)

        #     categories = [c for c in categories if c.get('features')]

        #     if plans_completed:
        #         production_notes = order.specialfeature_set.filter(sku_category__isnull=True).values_list('factory_description', flat=True)
        #     else:
        #         production_notes = order.specialfeature_set.all().values_list('customer_description', flat=True)

        #     is_html = bool(request.GET.get('is_html'))
        #     # For the first order initiate the list of dictionary and for all the others simply append dict to the list
        #     if i == 0:
        #         orders1=[{
        #             'order': order,
        #             'categories': categories,
        #             'company_name': settings.COMPANY_NAME,
        #             'production_notes': production_notes,
        #             'plans_completed': plans_completed,
        #         }]
        #     else:
        #         orders1.append({
        #             'order': order,
        #             'categories': categories,
        #             'company_name': settings.COMPANY_NAME,
        #             'production_notes': production_notes,
        #             'plans_completed': plans_completed,
        #         })
        #     i += 1
        #     # print(i,' : ', order.id , ' : ', datetime.now())
        # for i in range(10):
        #     print(i)
        #     time.sleep(2)
        # time.sleep(2)
        t.join()
        # orders1 = t.get()
        
        print(len(SchedulePDFView.global_orders))
        context_data={'orders1':SchedulePDFView.global_orders}
        print('Finished')
        # response = PDFTemplateResponse(
        #                     request=self.request,
        #                     template=self.template_name,
        #                     filename='file.pdf',
        #                     context=context_data,
        #                     cmd_options={'load-error-handling': 'ignore'})

        # with open("file.pdf", "wb") as f:
        #         f.write(response.rendered_content)

        is_html=False 


        # pdf = render_to_pdf('your/pdf/template.html', context)
        # with open("file.pdf", "wb") as f:
        #         f.write(pdf)

        # return render(request, self.template_name, context=context_data)

        # return HttpResponse(request,)

        
        response = self.render_printable(False, self.template_name, context_data, header_template="", pdf_options={"margin-top": "15mm", "orientation": "landscape"})

        # with open("file.pdf", "w") as f:


        #         f.write(response)

        self.save_pdf(response, 't1.pdf')

        return response 
    
    # Handle saving the document
    # This is what I'm using elsewhere where files are saved and it works there
    def save_pdf(self, file, filename):
        print(file)
        # with open(settings.MEDIA_URL + '/' + filename, 'wb+') as destination:
        #     for chunk in file.chunks():
        #         destination.write(chunk)
        print('Written file', settings.MEDIA_URL + filename )
        



    def background_process(self, request, my_orders):
        orders1=[]
        print(len(my_orders))
        i=0
        print(datetime.now())
        for myord in my_orders: 

            order = Order.objects.get(id=myord.id)

            plans_completed = order.get_finalization_status() == Order.STATUS_APPROVED

            categories = []
            top_level_categories_by_id = {}

            for skucategory in SKUCategory.top().skucategory_set.all().order_by('print_order'):
                category = {
                    'name': skucategory.name,
                    'print_order': skucategory.print_order,
                    'features': [],
                    'extras': [],
                    'special_features': [],
                }

                categories.append(category)
                top_level_categories_by_id[skucategory.id] = category

            special_feature_overrides = []

            for ordersku in order.ordersku_set.all().prefetch_related('sku', 'sku__sku_category'):
                # If a SeriesSKU doesn't exist, we show it in red.
                try:
                    seriessku = SeriesSKU.objects.get(series=order.orderseries.series, sku=ordersku.sku)
                except SeriesSKU.DoesNotExist:
                    seriessku = None

                if seriessku and not seriessku.is_visible_on_spec_sheet:
                    continue

                cat = ordersku.sku.sku_category
                while cat.id not in top_level_categories_by_id:
                    cat = cat.parent

                key = 'features'

                item = {
                    'red': not seriessku or ordersku.base_availability_type != SeriesSKU.AVAILABILITY_STANDARD,
                    'description': ordersku.sku.name,
                }

                if plans_completed:
                    # If a special feature is defined for this item, use the special feature description
                    try:
                        special_feature = order.specialfeature_set.get(sku_category=ordersku.sku.sku_category)
                        special_feature_overrides.append(special_feature.id)
                        item = {
                            'red': True,
                            'description': special_feature.factory_description,
                        }
                    except SpecialFeature.DoesNotExist:
                        pass

                if ordersku.base_availability_type == SeriesSKU.AVAILABILITY_OPTION:
                    key = 'extras'
                elif ordersku.base_availability_type == SeriesSKU.AVAILABILITY_SELECTION:
                    item['department'] = ordersku.sku.sku_category.name

                top_level_categories_by_id[cat.id][key].append(item)

            # Add any departments missing selections if order is not finalised
            if order.get_finalization_status() not in (Order.STATUS_APPROVED, Order.STATUS_PENDING):
                departments = SKUCategory.objects.filter(parent__parent=SKUCategory.top())
                availability_types = [
                    SeriesSKU.AVAILABILITY_STANDARD,
                    SeriesSKU.AVAILABILITY_SELECTION,
                    SeriesSKU.AVAILABILITY_UPGRADE
                ]
                selections = set([osku.sku.sku_category.id for osku in order.ordersku_set.filter(base_availability_type__in=availability_types)])
                departments_missing = set()
                for d in departments:
                    requires_selections = SeriesSKU.objects.filter(
                        is_visible_on_spec_sheet=True,
                        sku__sku_category=d,
                        series=order.orderseries.series,
                        availability_type__in=availability_types).count()
                    if requires_selections and d.id not in selections and d.id not in departments_missing:
                        departments_missing.add(d.id)
                        top_level_categories_by_id[d.parent.id]['features'].append({
                            'missing_selections': True,
                            'description': d.name,
                        })

            if plans_completed:
                for special_feature in order.specialfeature_set.filter(sku_category__isnull=False).exclude(id__in=special_feature_overrides).prefetch_related('sku_category'):
                    cat = special_feature.sku_category
                    while cat.id not in top_level_categories_by_id:
                        cat = cat.parent

                    top_level_categories_by_id[cat.id]['special_features'].append(special_feature.factory_description)

            categories = [c for c in categories if c.get('features')]

            if plans_completed:
                production_notes = order.specialfeature_set.filter(sku_category__isnull=True).values_list('factory_description', flat=True)
            else:
                production_notes = order.specialfeature_set.all().values_list('customer_description', flat=True)

            # is_html = bool(request.GET.get('is_html'))
            # For the first order initiate the list of dictionary and for all the others simply append dict to the list
            if i == 0:
                orders1=[{
                    'order': order,
                    'categories': categories,
                    'company_name': settings.COMPANY_NAME,
                    'production_notes': production_notes,
                    'plans_completed': plans_completed,
                }]
            else:
                orders1.append({
                    'order': order,
                    'categories': categories,
                    'company_name': settings.COMPANY_NAME,
                    'production_notes': production_notes,
                    'plans_completed': plans_completed,
                })
            i += 1
            # print(i,' : ', order.id , ' : ', datetime.now())
        
        SchedulePDFView.global_orders = orders1
        print('Completed',len(SchedulePDFView.global_orders))
        print(datetime.now())
        context_data={'orders1':SchedulePDFView.global_orders}

        # return orders1
        # context_data={'orders1':orders1}

        # return self.render_printable(False,self.template_name, context_data, header_template="", pdf_options={"margin-top": "15mm", "orientation": "landscape"})


class ContractorExportView(ExportCSVMixin, PermissionRequiredMixin, View):
    permission_required = 'schedule.export_schedule'

    def get_file_name(self):
        return self.contractor_export.name

    def get_complete_file_name(self):
        return '{0} {1}-{2}'.format(self.get_file_name(),
                                    self.date_from.strftime(settings.FORMAT_DATE_MONTH),
                                    self.date_to.strftime(settings.FORMAT_DATE_MONTH))

    def get_rows(self, table=None):

        rows = [
            [
                order.build.build_order.production_month.strftime(settings.FORMAT_DATE_MONTH),
                str(order.build.build_order.order_number),
                order.build.build_date.strftime(settings.FORMAT_DATE) if order.build.build_date else '',
                get_status(order),
                str(order.id),
                order.chassis,
                order.get_series_code(),
                '',
             ]  

            for order in self.orders
        ]

        cols = [
            [ 
            list(self.getrow(order)),
            ]

            for order in self.orders
         ]


        i=0
        for row in rows:
            for c in cols[i]: 
                row.extend(c)
            i += 1

        # for r in rows:
        #     print(r)
        return rows

    def getrow(self,order):
        sku_row=''
        for column in self.export_columns:
            sku_row +=str(self._get_sku_description(order, column.department_id, column.contractor_description_field)) + ','

        sku_row = sku_row.replace('(','').replace(')','')  
        sku_row = sku_row.strip('"').strip("'")

        sku_list = sku_row.split(",") if sku_row else None

        return list(sku_list)



    def get_headers(self, table=None):

        # First all the columns are extracted
        
        headers = ['Schedule Month',
                   'Schedule #',
                   'Production Date',
                   'Status',
                   'Order #',
                   'Chassis #',
                   'Model / Series',
                   '',
                   ]

        # Then all the extra columns are got with 'Code' prefix before each column
        extra_columns=[ ['Code', column.name] for column in self.export_columns]

        # Now extend the headers list to add the items in extra_columns to the headers

        for col_name in extra_columns: 
            headers.extend(col_name)

        return headers

    def get(self, request, unit_id, export_id, date_from, date_to):
        self.contractor_export = ContractorScheduleExport.objects.get(id=export_id)
        self.export_columns = self.contractor_export.contractorscheduleexportcolumn_set.all()
        self.date_from = parse_date(date_from + '-01')
        self.date_to = parse_date(date_to + '-01')
        self.production_unit = unit_id

        if date_from > date_to:
            return HttpResponseBadRequest("The start date is greater than the end date.")

        self.orders = (Order.objects
            .filter(
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
            )
            .order_by('build__build_order__production_month', 'build__build_order__order_number')
            .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
            )
            .prefetch_related(
                'specialfeature_set',
                'ordersku_set__sku',
            )
        )
        
        self.sskus = {(series, sku): desc for desc, sku, series in SeriesSKU.objects.values_list('contractor_description', 'sku_id', 'series_id')}
        
        return self.write_csv()


    def _get_sku_description(self, order, department_id, sku_field):
        """
        If a special feature is defined for this department, return the special feature description.

        Only one sku should be set per department, but technically several OPTION can be added in addition to a STANDARD, SELECTION or UPGRADE one.
        If a contractor description is set for this specific series_sku, return it.
        If it exists, find the first non-OPTION sku for the order, and return its `sku_field`
        If it exists, find the first OPTION sku for the order, and return its `sku_field`

        Otherwise, return empty string
        """

        # This function is executed for every export_column for every order in the export.
        # Using queryset.all() with filtering in python instead of queryset.filter() prevents an extra query by using the prefetched data

        special_features_for_department = [special_feature for special_feature in order.specialfeature_set.all() if special_feature.sku_category_id == department_id]
        if special_features_for_department:
            strip_special_value = str(special_features_for_department[0].factory_description).replace(',','').strip('\'') 
            return None,strip_special_value

        # Get the appropriate sku
        orderskus = [osku for osku in order.ordersku_set.all() if osku.sku.sku_category_id == department_id]
        if not orderskus:
            return ','

        non_option_skus = [osku.sku for osku in orderskus if osku.base_availability_type != SeriesSKU.AVAILABILITY_OPTION]
        if non_option_skus:
            sku = non_option_skus[0]
        else:
            sku = orderskus[0].sku

        desc = self.sskus[order.orderseries.series_id, sku.id]

        sku_data = str( desc or getattr(sku, sku_field) or '')

        sku_desc =  str(sku_data)  
        
        sku_desc = str(sku_desc).replace('[','').replace('(','').replace(')','').replace("'",'').replace(']','').replace('"','').replace(',','')
        
        sku_desc = sku_desc.replace('"','').replace("'",'')
        sku_desc = str(sku.code) + "," + sku_desc 
        sku_desc = sku_desc.strip('"').strip("'")
        
        return sku_desc

######################     ScheduleTransportDashboardCSVView     ##################
def get_special_feature_status(order):
    status = order.get_special_features_status()
    if status == Order.STATUS_PENDING:
        return 'pending'
    if status == Order.STATUS_APPROVED:
        return 'approved'
    if status == Order.STATUS_REJECTED:
        return 'rejected'
    return 'empty'


def get_status_string(order):
    if order.order_cancelled is not None:
        return 'cancelled'

    if order.get_finalization_status() != Order.STATUS_APPROVED:
        return 'not_finalized'

    order_document_types = order.get_current_document_types()
    if OrderDocument.DOCUMENT_CHASSIS_PLAN in order_document_types and OrderDocument.DOCUMENT_FACTORY_PLAN in order_document_types:
        return 'plans_completed'

    customer_approval_status = order.get_customer_plan_status()

    if customer_approval_status in (Order.STATUS_NONE, Order.STATUS_REJECTED):
        return 'pending_draft'

    if customer_approval_status == Order.STATUS_PENDING:
        return 'pending_customer'

    if customer_approval_status == Order.STATUS_APPROVED:
        return 'customer_approved'

    return 'unknown'


def planned_days(from_date, add_days):
    business_days_to_add = add_days
    current_date = from_date
    while business_days_to_add > 1:
        current_date += timedelta(days=1)
        weekday = current_date.weekday()
        if weekday >= 5: # sunday = 6
            continue
        business_days_to_add -= 1
    return current_date

def get_status_of_order(orderid):
    order_status = Order.objects.get(id= orderid)
    build_status = Build.objects.get(order_id = orderid)

    try:
        ordertransport_status = OrderTransport.objects.get(order_id = orderid)
    except OrderTransport.DoesNotExist :
        obj = OrderTransport(order_id = orderid)
        obj.save()
        ordertransport_status = OrderTransport.objects.get(order_id = orderid)

    if ordertransport_status.actual_production_date:
        
        if order_status.dispatch_date_actual:
            return 'Dispatched'
        elif ordertransport_status.hold_caravans:
            return 'On Hold'
        elif ordertransport_status.final_qc_date:
            return 'Ready For Dispatch'
        elif ordertransport_status.watertest_date:
            return 'QC' 
        elif ordertransport_status.detailing_date:    
            return 'Ready for Water Test'
        elif ordertransport_status.finishing:
            return 'Ready For Detailing Canopy'
        elif ordertransport_status.aluminium:
            return 'Finishing'
        elif ordertransport_status.plumbing_date:
            return 'Aluminium / Fit Off'
        elif ordertransport_status.prewire_section:
            return 'Plumbing'
        elif ordertransport_status.building:
            return 'Pre-Wire'
        elif ordertransport_status.chassis_section:
            return 'Building'
        elif ordertransport_status.actual_production_date:
            return 'Chassis'
        else:
            return 'Awaiting Production'
    else:
        return 'Awaiting Production'

def get_hold_status(orderid):
    try:
        ordertransport_status = OrderTransport.objects.get(order_id = orderid)
    except OrderTransport.DoesNotExist :
        obj = OrderTransport(order_id = orderid)
        obj.save()
        ordertransport_status = OrderTransport.objects.get(order_id = orderid)
    if ordertransport_status.hold_caravans:
        return 'On Hold'
    else:
        return

def pending_in_current_status(orderid):

    order_status = Order.objects.get(id= orderid)
    build_status = Build.objects.get(order_id = orderid)
    current_date = date.today()

    try:
        ordertransport_status = OrderTransport.objects.get(order_id = orderid)
    except OrderTransport.DoesNotExist :
        obj = OrderTransport(order_id = orderid)
        obj.save()
        ordertransport_status = OrderTransport.objects.get(order_id = orderid)

    if order_status.dispatch_date_actual:
        return ''

    else:

        if ordertransport_status.final_qc_date is not None:
            from_date = ordertransport_status.final_qc_date
        elif build_status.qc_date_actual is not None:
            from_date = build_status.qc_date_actual
        elif ordertransport_status.weigh_bridge_date is not None:
            from_date = ordertransport_status.weigh_bridge_date
        elif ordertransport_status.watertest_date is not None:
            from_date = ordertransport_status.watertest_date
        elif ordertransport_status.detailing_date is not None:
            from_date = ordertransport_status.detailing_date    
        elif ordertransport_status.finishing is not None:
            from_date = ordertransport_status.finishing
        elif ordertransport_status.aluminium is not None:
            from_date = ordertransport_status.aluminium
        elif ordertransport_status.building is not None:
            from_date = ordertransport_status.building
        elif ordertransport_status.chassis_section is not None:
            from_date = ordertransport_status.chassis_section
        elif ordertransport_status.actual_production_date is not None:
            from_date = ordertransport_status.actual_production_date
        else:
            return ''

        n = 0
        
        while current_date > from_date:
            from_date += timedelta(days=1)
            
            weekday = from_date.weekday()
            if weekday >= 5: # sunday = 6
                continue
            n +=1

        return n


class ProductionDashboardCSVView(ExportCSVMixin, PermissionRequiredMixin, View):

    permission_required = 'schedule.export_schedule' # Check

    def get_file_name(self):
        return 'Production Dashboard Export for' # Check

    def get_complete_file_name(self):
        return '{0} {1} {2}'.format(self.get_file_name(),
                                    self.category,
                                    self.date_from.strftime(settings.FORMAT_DATE_MONTH))

    def get_headers(self, table=None):
        
        headers = [
            'MONTH',
            'CHASSIS',
            'ORDER_ID',
            'MODEL_SERIES',
            'DEALERSHIP',
            'PLANNED_PRODUCTION',
            'ACTUAL_PRODUCTION',
            'CHASSIS_SECTION',
            'CHASSIS_SECTION_COMMENTS',
            'BUILDING',
            'BUILDING_COMMENTS',
            'PREWIRE_SECTION',
            'PREWIRE_COMMENTS',
            'PLUMBING_SECTION',
            'PLUMBING_COMMENTS',
            'ALUMINIUM / FIT OFF',
            'ALUMINIUM_COMMENTS',
            'FINISHING',
            'FINISHING_COMMENTS',
            'DETAILING_CANOPY',
            'DETAILING_COMMENTS',
            'WATER_TEST',
            'WATER_TEST_COMMENTS',
            'QC',
            'QC COMMENTS',
            'PLANNED_DISPATCH',
            'ACTUAL_DISPATCH',
            'DISPATCH_COMMENTS',
            'HOLD_CARAVANS',
            'STATUS',
            'NO. OF DAYS PENDING IN CURRENT STATUS'
        ]
        return headers

    def get_rows(self, table=None):

        rows = [
            [
                order.build.build_order.production_month.strftime(settings.FORMAT_DATE_MONTH),
                str(order.chassis) if order.chassis else '',
                '#{}'.format(order.id),
                order.custom_series_code or order.orderseries.series.code,
                order.dealership.name,
                order.build.build_date,
                order.ordertransport.actual_production_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.chassis_section if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.chassis_section_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.building if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.building_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.prewire_section if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.prewire_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.plumbing_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.plumbing_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.aluminium if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.aluminium_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.finishing if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.finishing_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.detailing_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.detailing_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.watertest_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.watertest_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.ordertransport.final_qc_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                str(order.ordertransport.final_qc_comments) if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                order.dispatch_date_planned if order.dispatch_date_planned else planned_days(order.build.build_date, 16) if order.build.build_date else None,
                order.dispatch_date_actual,
                order.ordertransport.dispatch_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                get_hold_status(order.id),
                get_status_of_order(order.id),
                pending_in_current_status(order.id),
            ]
            for order in self.orders
            ]

        return rows


    def get(self, request, unit_id, date_from, date_to, category):

        self.date_from = parse_date(date_from + '-01')
        self.date_to = parse_date(date_to + '-01')
        self.category = category
        self.production_unit = unit_id

        if date_from > date_to:
            return HttpResponseBadRequest("The start date is greater than the end date.")


    ################# Get all Data #########################

        if self.category == 'all':

            self.orders = Order \
                .objects \
                .filter(
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)

        ########### Get awaiting production data ############

        if self.category == 'awaiting_production':

            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = True,
                ordertransport__chassis_section__isnull = True,
                build__qc_date_actual__isnull = True,
                ordertransport__watertest_date__isnull = True,
                ordertransport__detailing_date__isnull = True,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)

        ########### Get awaiting chassis data ############

        if self.category == 'awaiting_chassis':

            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = False,
                ordertransport__chassis_section__isnull = True,
                ordertransport__building__isnull = True,
                ordertransport__prewire_section__isnull = True,
                ordertransport__plumbing_date__isnull = True,
                ordertransport__aluminium__isnull = True,
                ordertransport__finishing__isnull = True,
                ordertransport__detailing_date__isnull = True,
                ordertransport__watertest_date__isnull = True,
                build__qc_date_actual__isnull = True,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)

        ########### Get awaiting Building data ############

        if self.category == 'awaiting_building':

            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = False,
                ordertransport__chassis_section__isnull = False,
                ordertransport__building__isnull = True,
                ordertransport__prewire_section__isnull = True,
                ordertransport__plumbing_date__isnull = True,
                ordertransport__aluminium__isnull = True,
                ordertransport__finishing__isnull = True,
                ordertransport__watertest_date__isnull = True,
                ordertransport__detailing_date__isnull = True,
                build__qc_date_actual__isnull = True,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)

        ########### Get awaiting Pre-wire data ############

        if self.category == 'awaiting_prewire':

            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = False,
                ordertransport__chassis_section__isnull = False,
                ordertransport__building__isnull = False,
                ordertransport__prewire_section__isnull = True,
                ordertransport__plumbing_date__isnull = True,
                ordertransport__aluminium__isnull = True,
                ordertransport__finishing__isnull = True,
                ordertransport__watertest_date__isnull = True,
                ordertransport__detailing_date__isnull = True,
                build__qc_date_actual__isnull = True,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)

        ########### Get awaiting Plumbing data ############

        if self.category == 'awaiting_plumbing':

            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = False,
                ordertransport__chassis_section__isnull = False,
                ordertransport__building__isnull = False,
                ordertransport__prewire_section__isnull = False,
                ordertransport__plumbing_date__isnull = True,
                ordertransport__aluminium__isnull = True,
                ordertransport__finishing__isnull = True,
                ordertransport__watertest_date__isnull = True,
                ordertransport__detailing_date__isnull = True,
                build__qc_date_actual__isnull = True,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)


        ########### Get awaiting Aluminium  data ############

        if self.category == 'awaiting_aluminium':

            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = False,
                ordertransport__chassis_section__isnull = False,
                ordertransport__building__isnull = False,
                ordertransport__prewire_section__isnull = False,
                ordertransport__plumbing_date__isnull = False,
                ordertransport__aluminium__isnull = True,
                ordertransport__finishing__isnull = True,
                ordertransport__watertest_date__isnull = True,
                ordertransport__detailing_date__isnull = True,
                build__qc_date_actual__isnull = True,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)

        ########### Get awaiting finishing  data ############

        if self.category == 'awaiting_finishing':

            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = False,
                ordertransport__chassis_section__isnull = False,
                ordertransport__building__isnull = False,
                ordertransport__prewire_section__isnull = False,
                ordertransport__plumbing_date__isnull = False,
                ordertransport__aluminium__isnull = False,
                ordertransport__finishing__isnull = True,
                ordertransport__watertest_date__isnull = True,
                ordertransport__detailing_date__isnull = True,
                build__qc_date_actual__isnull = True,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)

                ########### Get Detailing Data ##############
        if self.category == 'awaiting_detailing':
            
            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = False,
                ordertransport__chassis_section__isnull = False,
                ordertransport__building__isnull = False,
                ordertransport__prewire_section__isnull = False,
                ordertransport__plumbing_date__isnull = False,
                ordertransport__aluminium__isnull = False,
                ordertransport__finishing__isnull = False,
                ordertransport__detailing_date__isnull = True,
                ordertransport__watertest_date__isnull = True,
                build__qc_date_actual__isnull = True,
                ordertransport__final_qc_date__isnull =True,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)

        ########### Get Water test Data ##############
        if self.category == 'awaiting_watertest':
            
            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = False,
                ordertransport__chassis_section__isnull = False,
                ordertransport__building__isnull = False,
                ordertransport__prewire_section__isnull = False,
                ordertransport__plumbing_date__isnull = False,
                ordertransport__aluminium__isnull = False,
                ordertransport__finishing__isnull = False,
                ordertransport__detailing_date__isnull = False,
                ordertransport__watertest_date__isnull = True,
                ordertransport__final_qc_date__isnull =True,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)


        ########### Get awaiting_qc Data ##############

        if self.category == 'awaiting_qc':
            
            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = False,
                ordertransport__chassis_section__isnull = False,
                ordertransport__building__isnull = False,
                ordertransport__prewire_section__isnull = False,
                ordertransport__plumbing_date__isnull = False,
                ordertransport__aluminium__isnull = False,
                ordertransport__finishing__isnull = False,
                ordertransport__detailing_date__isnull = False,
                ordertransport__watertest_date__isnull = False,
                build__qc_date_actual__isnull = True,
                ordertransport__final_qc_date__isnull =True,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)


        ################# Get pending for Final QC data #####################

        if self.category == 'awaiting_final_qc':

            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = False,
                ordertransport__chassis_section__isnull = False,
                ordertransport__building__isnull = False,
                ordertransport__prewire_section__isnull = False,
                ordertransport__plumbing_date__isnull = False,
                ordertransport__aluminium__isnull = False,
                ordertransport__finishing__isnull = False,
                ordertransport__detailing_date__isnull = False,
                ordertransport__watertest_date__isnull = False,
                # build__qc_date_actual__isnull = True,
                ordertransport__final_qc_date__isnull =True,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)

        ########Get dispatched data ######

        if self.category == 'dispatched':

            self.orders = Order \
                .objects \
                .filter(
                ordertransport__watertest_date__isnull = False,
                ordertransport__detailing_date__isnull = False,
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                dispatch_date_actual__isnull = False,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)

        ################# Get pending for dispatch data #####################

        if self.category == 'pending_for_dispatch':

            self.orders = Order \
                .objects \
                .filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month__gte=self.date_from,
                build__build_order__production_month__lte=self.date_to,
                build__build_order__production_unit=self.production_unit,
                ordertransport__actual_production_date__isnull = False,
                ordertransport__watertest_date__isnull = False,
                ordertransport__detailing_date__isnull = False,
                ordertransport__final_qc_date__isnull =False,
                dispatch_date_actual__isnull = True,
                ) \
                .order_by('build__build_order__production_month', 'build__build_order__order_number') \
                .select_related(
                'build__build_order',
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'show',
                'dealership',
                'customer',
                'build__drafter',
            ).prefetch_related('orderdocument_set',)


        return self.write_csv()


# DelayDashboardCSVView

class DelayDashboardCSVView(ExportCSVMixin, PermissionRequiredMixin, View):

    permission_required = 'schedule.export_schedule' # Check

    def get_file_name(self):
        return 'Delay Dashboard Export for' # Check

    def get_complete_file_name(self):
        self.date_from= date.today()
        return '{0} {1} {2}'.format(self.get_file_name(),
                                    self.category,
                                    self.date_from.strftime(settings.FORMAT_DATE_MONTH))

    def get_headers(self, table=None):
        
        if(self.report_type == 'all'):
            headers = [
            'ORDER ID',
            'PRODUCTION MONTH',
            'SCHEDULE',
            'CHASSIS',
            'MODEL SERIES',
            'DEALERSHIP',
            'DELAYED WITHIN PRODUCTION',
            'PLANNED PRODUCTION',
            'PLANNED DISPATCH',
            'ACTUAL PRODUCTION',
            'DELAYED TO START PRODUCTION',
            'PLANNED CHASSIS',
            'ACTUAL CHASSIS',
            'CHASSIS DELAY ',
            'PLANNED BUILDING',
            'ACTUAL BUILDING',
            'BUILDING DELAY',
            'PLANNED PREWIRE',
            'ACTUAL PREWIRE',
            'PREWIRE DELAY',
            'PLANNED PLUMBING',
            'ACTUAL PLUMBING',
            'PLUMBING DELAY',
            'PLANNED ALUMINIUM',
            'ACTUAL ALUMINIUM',
            'ALUMINIUM DELAY',
            'PLANNED FINISHING',
            'ACTUAL FINISHING',
            'FINISHING DELAY',
            'PLANNED DETAILING',
            'ACTUAL DETAILING',
            'DETAILING DELAY',
            'PLANNED WATERTEST',
            'ACTUAL  WATERTEST',
            'WATER_TEST DELAY',
            'PLANNED QC',
            'ACTUAL QC',
            'QC DELAY',
            ]
        
        if(self.report_type == 'chassis'):
            headers = [
            'ORDER ID',
            'PRODUCTION MONTH',
            'SCHEDULE',
            'CHASSIS',
            'MODEL SERIES',
            'DEALERSHIP',
            'DELAYED WITHIN PRODUCTION',
            'PLANNED PRODUCTION',
            'PLANNED DISPATCH',
            'ACTUAL PRODUCTION',
            'DELAYED TO START PRODUCTION',
            'PLANNED CHASSIS',
            'ACTUAL CHASSIS',
            'CHASSIS DELAY DAYS',
            ]

        if(self.report_type == 'building'):
            headers = [
            'ORDER ID',
            'PRODUCTION MONTH',
            'SCHEDULE',
            'CHASSIS',
            'MODEL SERIES',
            'DEALERSHIP',
            'DELAYED WITHIN PRODUCTION',
            'PLANNED PRODUCTION',
            'PLANNED DISPATCH',
            'ACTUAL PRODUCTION',
            'DELAYED TO START PRODUCTION',
            'PLANNED CHASSIS',
            'ACTUAL CHASSIS',
            'CHASSIS DELAY ',
            'PLANNED BUILDING',
            'ACTUAL BUILDING',
            'BUILDING DELAY',
            
            ]
        
        if(self.report_type == 'prewire'):
            headers = [
            'ORDER ID',
            'PRODUCTION MONTH',
            'SCHEDULE',
            'CHASSIS',
            'MODEL SERIES',
            'DEALERSHIP',
            'DELAYED WITHIN PRODUCTION',
            'PLANNED PRODUCTION',
            'PLANNED DISPATCH',
            'ACTUAL PRODUCTION',
            'DELAYED TO START PRODUCTION',
            'PLANNED CHASSIS',
            'ACTUAL CHASSIS',
            'CHASSIS DELAY ',
            'PLANNED BUILDING',
            'ACTUAL BUILDING',
            'BUILDING DELAY',
            'PLANNED PREWIRE',
            'ACTUAL PREWIRE',
            'PREWIRE DELAY',
            
            ]

        if(self.report_type == 'plumbing'):
            headers = [
           'ORDER ID',
            'PRODUCTION MONTH',
            'SCHEDULE',
            'CHASSIS',
            'MODEL SERIES',
            'DEALERSHIP',
            'DELAYED WITHIN PRODUCTION',
            'PLANNED PRODUCTION',
            'PLANNED DISPATCH',
            'ACTUAL PRODUCTION',
            'DELAYED TO START PRODUCTION',
            'PLANNED CHASSIS',
            'ACTUAL CHASSIS',
            'CHASSIS DELAY ',
            'PLANNED BUILDING',
            'ACTUAL BUILDING',
            'BUILDING DELAY',
            'PLANNED PREWIRE',
            'ACTUAL PREWIRE',
            'PREWIRE DELAY',
            'PLANNED PLUMBING',
            'ACTUAL PLUMBING',
            'PLUMBING DELAY',
            
            ]

        if(self.report_type == 'aluminium'):
            headers = [
            'ORDER ID',
            'PRODUCTION MONTH',
            'SCHEDULE',
            'CHASSIS',
            'MODEL SERIES',
            'DEALERSHIP',
            'DELAYED WITHIN PRODUCTION',
            'PLANNED PRODUCTION',
            'PLANNED DISPATCH',
            'ACTUAL PRODUCTION',
            'DELAYED TO START PRODUCTION',
            'PLANNED CHASSIS',
            'ACTUAL CHASSIS',
            'CHASSIS DELAY ',
            'PLANNED BUILDING',
            'ACTUAL BUILDING',
            'BUILDING DELAY',
            'PLANNED PREWIRE',
            'ACTUAL PREWIRE',
            'PREWIRE DELAY',
            'PLANNED PLUMBING',
            'ACTUAL PLUMBING',
            'PLUMBING DELAY',
            'PLANNED ALUMINIUM',
            'ACTUAL ALUMINIUM',
            'ALUMINIUM DELAY',
            
            ]

        if(self.report_type == 'finishing'):
            headers = [
            'ORDER ID',
            'PRODUCTION MONTH',
            'SCHEDULE',
            'CHASSIS',
            'MODEL SERIES',
            'DEALERSHIP',
            'DELAYED WITHIN PRODUCTION',
            'PLANNED PRODUCTION',
            'PLANNED DISPATCH',
            'ACTUAL PRODUCTION',
            'DELAYED TO START PRODUCTION',
            'PLANNED CHASSIS',
            'ACTUAL CHASSIS',
            'CHASSIS DELAY ',
            'PLANNED BUILDING',
            'ACTUAL BUILDING',
            'BUILDING DELAY',
            'PLANNED PREWIRE',
            'ACTUAL PREWIRE',
            'PREWIRE DELAY',
            'PLANNED PLUMBING',
            'ACTUAL PLUMBING',
            'PLUMBING DELAY',
            'PLANNED ALUMINIUM',
            'ACTUAL ALUMINIUM',
            'ALUMINIUM DELAY',
            'PLANNED FINISHING',
            'ACTUAL FINISHING',
            'FINISHING DELAY',
            ]

        if(self.report_type == 'detailing'):
            headers = [
            'ORDER ID',
            'PRODUCTION MONTH',
            'SCHEDULE',
            'CHASSIS',
            'MODEL SERIES',
            'DEALERSHIP',
            'DELAYED WITHIN PRODUCTION',
            'PLANNED PRODUCTION',
            'PLANNED DISPATCH',
            'ACTUAL PRODUCTION',
            'DELAYED TO START PRODUCTION',
            'PLANNED CHASSIS',
            'ACTUAL CHASSIS',
            'CHASSIS DELAY ',
            'PLANNED BUILDING',
            'ACTUAL BUILDING',
            'BUILDING DELAY',
            'PLANNED PREWIRE',
            'ACTUAL PREWIRE',
            'PREWIRE DELAY',
            'PLANNED PLUMBING',
            'ACTUAL PLUMBING',
            'PLUMBING DELAY',
            'PLANNED ALUMINIUM',
            'ACTUAL ALUMINIUM',
            'ALUMINIUM DELAY',
            'PLANNED FINISHING',
            'ACTUAL FINISHING',
            'FINISHING DELAY',
            'PLANNED DETAILING',
            'ACTUAL DETAILING',
            'DETAILING DELAY',
            ]
            

        if(self.report_type == 'watertesting'):
            headers = [
                'ORDER ID',
                'PRODUCTION MONTH',
                'SCHEDULE',
                'CHASSIS',
                'MODEL SERIES',
                'DEALERSHIP',
                'DELAYED WITHIN PRODUCTION',
                'PLANNED PRODUCTION',
                'PLANNED DISPATCH',
                'ACTUAL PRODUCTION',
                'DELAYED TO START PRODUCTION',
                'PLANNED CHASSIS',
                'ACTUAL CHASSIS',
                'CHASSIS DELAY ',
                'PLANNED BUILDING',
                'ACTUAL BUILDING',
                'BUILDING DELAY',
                'PLANNED PREWIRE',
                'ACTUAL PREWIRE',
                'PREWIRE DELAY',
                'PLANNED PLUMBING',
                'ACTUAL PLUMBING',
                'PLUMBING DELAY',
                'PLANNED ALUMINIUM',
                'ACTUAL ALUMINIUM',
                'ALUMINIUM DELAY',
                'PLANNED FINISHING',
                'ACTUAL FINISHING',
                'FINISHING DELAY',
                'PLANNED DETAILING',
                'ACTUAL DETAILING',
                'DETAILING DELAY',
                'PLANNED WATERTEST',
                'ACTUAL  WATERTEST',
                'WATERTEST DELAY',
            ]

        if(self.report_type == 'finalqc'):
            headers = [
                        'ORDER ID',
                        'PRODUCTION MONTH',
                        'SCHEDULE',
                        'CHASSIS',
                        'MODEL SERIES',
                        'DEALERSHIP',
                        'DELAYED WITHIN PRODUCTION',
                        'PLANNED PRODUCTION',
                        'PLANNED DISPATCH',
                        'ACTUAL PRODUCTION',
                        'DELAYED TO START PRODUCTION',
                        'PLANNED CHASSIS',
                        'ACTUAL CHASSIS',
                        'CHASSIS DELAY ',
                        'PLANNED BUILDING',
                        'ACTUAL BUILDING',
                        'BUILDING DELAY',
                        'PLANNED PREWIRE',
                        'ACTUAL PREWIRE',
                        'PREWIRE DELAY',
                        'PLANNED PLUMBING',
                        'ACTUAL PLUMBING',
                        'PLUMBING DELAY',
                        'PLANNED ALUMINIUM',
                        'ACTUAL ALUMINIUM',
                        'ALUMINIUM DELAY',
                        'PLANNED FINISHING',
                        'ACTUAL FINISHING',
                        'FINISHING DELAY',
                        'PLANNED DETAILING',
                        'ACTUAL DETAILING',
                        'DETAILING DELAY',
                        'PLANNED WATERTEST',
                        'ACTUAL  WATERTEST',
                        'WATERTEST DELAY',
                        'PLANNED QC',
                        'ACTUAL QC',
                        'QC DELAY',
                    ]

        return headers

    def get_rows(self, table=None):

        if(self.report_type == 'all'):
            rows = [
                        [   
                                order['id'],
                                order['production_month'],
                                order['schno'],
                                order['chassis'],
                                order['model'] ,
                                order['dealership'],

                                order['roll_delay'],
                                
                                order['production_date'],
                                order['planned_dispatch_date'],
                                order['actual_production_date'],
                                order['estimated_delay'],
                                
                                order['planned_chassis'],
                                order['actual_chassis'],
                                order['chassis_delay'],


                                order['planned_building'],
                                order['actual_building'],
                                order['building_delay'],

                                order['planned_prewire'],
                                order['actual_prewire'],
                                order['prewire_delay'],
                                
                                order['planned_plumbing'],
                                order['actual_plumbing'],
                                order['plumbing_delay'],

                                order['planned_aluminium'],
                                order['actual_aluminium'],
                                order['aluminium_delay'],
                                 
                                order['planned_finishing'],
                                order['actual_finishing'],
                                order['finishing_delay'],

                                order['planned_detailing'],
                                order['actual_detailing'],
                                order['detailing_delay'],

                                order['planned_watertest'],
                                order['actual_watertest'],
                                order['watertest_delay'],

                                order['planned_final_qc'],
                                order['actual_final_qc'],
                                order['final_qc_delay']
                ]
                for order in self.delay_list
            ]


        if(self.report_type == 'chassis'):
            rows = [
                        [
                            order['id'], 
                            order['production_month'],
                            order['schno'],
                            order['chassis'],
                            order['model'] ,
                            order['dealership'],
                            order['roll_delay'],
                            order['production_date'],
                            order['planned_dispatch_date'],
                            order['actual_production_date'],
                            order['estimated_delay'],
                            order['planned_chassis'],
                            order['actual_chassis'],
                            order['chassis_delay']
                        ] 
                    for order in self.delay_list 
                    ]


        if(self.report_type == 'building'):
            rows = [
                        [   
                            order['id'],
                            order['production_month'],
                            order['schno'],
                            order['chassis'],
                            order['model'] ,
                            order['dealership'],

                            order['roll_delay'],
                            
                            order['production_date'],
                            order['planned_dispatch_date'],
                            order['actual_production_date'],
                            order['estimated_delay'],
                            
                            order['planned_chassis'],
                            order['actual_chassis'],
                            order['chassis_delay'],


                            order['planned_building'],
                            order['actual_building'],
                            order['building_delay'],
                                
                ]
                for order in self.delay_list
            ]
        
        if(self.report_type == 'prewire'):
            rows = [
                        [

                            order['id'],
                            order['production_month'],
                            order['schno'],
                            order['chassis'],
                            order['model'] ,
                            order['dealership'],

                            order['roll_delay'],
                            
                            order['production_date'],
                            order['planned_dispatch_date'],
                            order['actual_production_date'],
                            order['estimated_delay'],
                            
                            order['planned_chassis'],
                            order['actual_chassis'],
                            order['chassis_delay'],


                            order['planned_building'],
                            order['actual_building'],
                            order['building_delay'],

                            order['planned_prewire'],
                            order['actual_prewire'],
                            order['prewire_delay'],
                                                   
                ]
                for order in self.delay_list
            ]

        if(self.report_type == 'plumbing'):
            rows = [
                        [   
                               order['id'],
                                order['production_month'],
                                order['schno'],
                                order['chassis'],
                                order['model'] ,
                                order['dealership'],

                                order['roll_delay'],
                                
                                order['production_date'],
                                order['planned_dispatch_date'],
                                order['actual_production_date'],
                                order['estimated_delay'],
                                
                                order['planned_chassis'],
                                order['actual_chassis'],
                                order['chassis_delay'],


                                order['planned_building'],
                                order['actual_building'],
                                order['building_delay'],

                                order['planned_prewire'],
                                order['actual_prewire'],
                                order['prewire_delay'],
                                
                                order['planned_plumbing'],
                                order['actual_plumbing'],
                                order['plumbing_delay'],

                ]
                for order in self.delay_list
            ]


        if(self.report_type == 'aluminium'):
            rows = [
                        [   
                            order['id'],
                            order['production_month'],
                            order['schno'],
                            order['chassis'],
                            order['model'] ,
                            order['dealership'],

                            order['roll_delay'],
                            
                            order['production_date'],
                            order['planned_dispatch_date'],
                            order['actual_production_date'],
                            order['estimated_delay'],
                            
                            order['planned_chassis'],
                            order['actual_chassis'],
                            order['chassis_delay'],


                            order['planned_building'],
                            order['actual_building'],
                            order['building_delay'],

                            order['planned_prewire'],
                            order['actual_prewire'],
                            order['prewire_delay'],
                            
                            order['planned_plumbing'],
                            order['actual_plumbing'],
                            order['plumbing_delay'],

                            order['planned_aluminium'],
                            order['actual_aluminium'],
                            order['aluminium_delay'],
                             
                ]
                for order in self.delay_list
            ]

        if(self.report_type == 'finishing'):
            rows = [
                        [   
                            order['id'],
                            order['production_month'],
                            order['schno'],
                            order['chassis'],
                            order['model'] ,
                            order['dealership'],

                            order['roll_delay'],
                            
                            order['production_date'],
                            order['planned_dispatch_date'],
                            order['actual_production_date'],
                            order['estimated_delay'],
                            
                            order['planned_chassis'],
                            order['actual_chassis'],
                            order['chassis_delay'],


                            order['planned_building'],
                            order['actual_building'],
                            order['building_delay'],

                            order['planned_prewire'],
                            order['actual_prewire'],
                            order['prewire_delay'],
                            
                            order['planned_plumbing'],
                            order['actual_plumbing'],
                            order['plumbing_delay'],

                            order['planned_aluminium'],
                            order['actual_aluminium'],
                            order['aluminium_delay'],
                             
                            order['planned_finishing'],
                            order['actual_finishing'],
                            order['finishing_delay'],

                ]
                for order in self.delay_list
            ]

        if(self.report_type == 'detailing'):
            rows = [
                        [ 
                            order['id'],
                            order['production_month'],
                            order['schno'],
                            order['chassis'],
                            order['model'] ,
                            order['dealership'],

                            order['roll_delay'],
                            
                            order['production_date'],
                            order['planned_dispatch_date'],
                            order['actual_production_date'],
                            order['estimated_delay'],
                            
                            order['planned_chassis'],
                            order['actual_chassis'],
                            order['chassis_delay'],


                            order['planned_building'],
                            order['actual_building'],
                            order['building_delay'],

                            order['planned_prewire'],
                            order['actual_prewire'],
                            order['prewire_delay'],
                            
                            order['planned_plumbing'],
                            order['actual_plumbing'],
                            order['plumbing_delay'],

                            order['planned_aluminium'],
                            order['actual_aluminium'],
                            order['aluminium_delay'],
                             
                            order['planned_finishing'],
                            order['actual_finishing'],
                            order['finishing_delay'],

                            order['planned_detailing'],
                            order['actual_detailing'],
                            order['detailing_delay'],
                               
                ]
                for order in self.delay_list
            ]

        if(self.report_type == 'watertesting'):
            rows = [
                        [  
                          order['id'],
                                order['production_month'],
                                order['schno'],
                                order['chassis'],
                                order['model'] ,
                                order['dealership'],

                                order['roll_delay'],
                                
                                order['production_date'],
                                order['planned_dispatch_date'],
                                order['actual_production_date'],
                                order['estimated_delay'],
                                
                                order['planned_chassis'],
                                order['actual_chassis'],
                                order['chassis_delay'],


                                order['planned_building'],
                                order['actual_building'],
                                order['building_delay'],

                                order['planned_prewire'],
                                order['actual_prewire'],
                                order['prewire_delay'],
                                
                                order['planned_plumbing'],
                                order['actual_plumbing'],
                                order['plumbing_delay'],

                                order['planned_aluminium'],
                                order['actual_aluminium'],
                                order['aluminium_delay'],
                                 
                                order['planned_finishing'],
                                order['actual_finishing'],
                                order['finishing_delay'],

                                order['planned_detailing'],
                                order['actual_detailing'],
                                order['detailing_delay'],

                                order['planned_watertest'],
                                order['actual_watertest'],
                                order['watertest_delay'],
       
                ]
                for order in self.delay_list
            ]


        if(self.report_type == 'finalqc'):
            rows = [
                        [

                        order['id'],
                        order['production_month'],
                        order['schno'],
                        order['chassis'],
                        order['model'] ,
                        order['dealership'],

                        order['roll_delay'],
                        
                        order['production_date'],
                        order['planned_dispatch_date'],
                        order['actual_production_date'],
                        order['estimated_delay'],
                        
                        order['planned_chassis'],
                        order['actual_chassis'],
                        order['chassis_delay'],


                        order['planned_building'],
                        order['actual_building'],
                        order['building_delay'],

                        order['planned_prewire'],
                        order['actual_prewire'],
                        order['prewire_delay'],
                        
                        order['planned_plumbing'],
                        order['actual_plumbing'],
                        order['plumbing_delay'],

                        order['planned_aluminium'],
                        order['actual_aluminium'],
                        order['aluminium_delay'],
                         
                        order['planned_finishing'],
                        order['actual_finishing'],
                        order['finishing_delay'],

                        order['planned_detailing'],
                        order['actual_detailing'],
                        order['detailing_delay'],

                        order['planned_watertest'],
                        order['actual_watertest'],
                        order['watertest_delay'],

                        order['planned_final_qc'],
                        order['actual_final_qc'],
                        order['final_qc_delay']

                ]
                for order in self.delay_list
            ]

        return rows


    def get(self, request, category):

        self.category = category

        today = date.today()

    ################# Get all Data #########################
        self.orders = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            build__build_date__isnull =  False,
            ordertransport__actual_production_date__isnull = False,
            dispatch_date_actual__isnull = True,
            ) \
            .order_by('build__build_order__production_month', 'build__build_order__order_number') \
            .select_related(
            'build',
            'build__build_order',
            'orderseries',
            'orderseries__series',
            'orderseries__series__model',
            'ordertransport',
            'show',
            'dealership',
            'customer',
            'build__drafter',
        ).prefetch_related('orderdocument_set',)

        self.delay_list = [
                {   
                    'id':order.id,
                    'production_date': order.build.build_date,
                    'production_month': datetime.strptime(str(order.build.build_order.production_month),'%Y-%m-%d').strftime('%b-%Y'),
                    'schno':order.build.build_order.order_number,
                    'production_unit':order.orderseries.production_unit,
                    'dealership':order.dealership.name,
                    'model':order.orderseries.series.name,
                    'series_type':order.orderseries.series.series_type,
                    'actual_production_date' : order.ordertransport.actual_production_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                    'chassis': getchassisno(order),
                    'chassis_section' : order.ordertransport.chassis_section if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                    'building' : order.ordertransport.building if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                    'prewire_section' : order.ordertransport.prewire_section if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                    'plumbing_date' : order.ordertransport.plumbing_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                    'aluminium_date' : order.ordertransport.aluminium if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                    'finishing' : order.ordertransport.finishing if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                    'planned_qc_date': order.build.qc_date_planned,
                    'watertest_date' : order.ordertransport.watertest_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                    'detailing_date' : order.ordertransport.detailing_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                    'final_qc_date' : order.ordertransport.final_qc_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                    'actual_qc_date' : order.build.qc_date_actual,
                    'production_unit':order.orderseries.production_unit,
                    'planned_dates': get_planned_dates(order.build.build_date,order.id,order.orderseries.production_unit,order.ordertransport.actual_production_date if OrderTransport.objects.filter(order_id= order.id).exists() else None)
                }
                for order in self.orders
            ]

        self.delay_list = [
                    {   
                        'id':order['id'],
                        'production_month': order['production_month'],
                        'schno':order['schno'],
                        'dealership':order['dealership'],
                        'model':order['model'],
                        'series_type':order['series_type'],
                        'production_unit': order['production_unit'],
                        'chassis': order['chassis'],
                        
                        'production_date': ' ' + str(convert_date_uniform(order['production_date'])),
                        'actual_production_date': ' ' + str(convert_date_uniform(order['actual_production_date'])),
                        'planned_dispatch_date': ' ' + str(convert_date_uniform(order['planned_dates']['planned_dispatch_date'])),
                        
                        'estimated_delay': getdiff(order['actual_production_date'], order['production_date'],order['production_date'],order['id'],order['production_unit'],1),

                        'actual_chassis':convert_date_uniform(order['chassis_section']),
                        'planned_chassis':convert_date_uniform(order['planned_dates']['planned_chassis_date']),
                        'chassis_delay': getdiff(order['chassis_section'],order['planned_dates']['planned_chassis_date'],order['actual_production_date'],order['id'],order['production_unit'],1),
                        
                        'actual_building':convert_date_uniform(order['building']),
                        'planned_building':convert_date_uniform(order['planned_dates']['planned_building_date']),
                        'building_delay': getdiff(order['building'],order['planned_dates']['planned_building_date'],order['chassis_section'],order['id'],order['production_unit'],1),
                        
                        'actual_prewire':convert_date_uniform(order['prewire_section']),
                        'planned_prewire':convert_date_uniform(order['planned_dates']['planned_prewire_date']),
                        'prewire_delay': getdiff(order['prewire_section'],order['planned_dates']['planned_prewire_date'],order['building'],order['id'],order['production_unit'],1),

                        'actual_plumbing':convert_date_uniform(order['plumbing_date']),
                        'planned_plumbing':convert_date_uniform(order['planned_dates']['planned_plumbing_date']),
                        'plumbing_delay': getdiff(order['plumbing_date'],order['planned_dates']['planned_plumbing_date'],order['prewire_section'],order['id'],order['production_unit'],1),


                        'actual_aluminium':convert_date_uniform(order['aluminium_date']),
                        'planned_aluminium':convert_date_uniform(order['planned_dates']['planned_aluminium_date']),
                        'aluminium_delay': getdiff(order['aluminium_date'],order['planned_dates']['planned_aluminium_date'],order['plumbing_date'],order['id'],order['production_unit'],1),
                        
                        'actual_finishing':convert_date_uniform(order['finishing']),
                        'planned_finishing':convert_date_uniform(order['planned_dates']['planned_finishing_date']),
                        'finishing_delay': getdiff(order['finishing'],order['planned_dates']['planned_finishing_date'],order['aluminium_date'],order['id'],order['production_unit'],2),

                        'actual_detailing':convert_date_uniform(order['detailing_date']),
                        'planned_detailing':convert_date_uniform(order['planned_dates']['planned_detailing_date']),
                        'detailing_delay': getdiff(order['detailing_date'],order['planned_dates']['planned_detailing_date'],order['finishing'],order['id'],order['production_unit'],1),

                        'actual_watertest':convert_date_uniform(order['watertest_date']),
                        'planned_watertest':convert_date_uniform(order['planned_dates']['planned_watertest_date']),
                        'watertest_delay': getdiff(order['watertest_date'],order['planned_dates']['planned_watertest_date'],order['detailing_date'],order['id'],order['production_unit'],1),

                        'actual_final_qc':convert_date_uniform(order['final_qc_date']),
                        'planned_final_qc':convert_date_uniform(order['planned_dates']['planned_final_qc_date']),
                        'final_qc_delay': getdiff(order['final_qc_date'],order['planned_dates']['planned_final_qc_date'],order['watertest_date'],order['id'],order['production_unit'],4),

                    }
                    for order in self.delay_list
                ]

        self.delay_list = [
                    {   
                        'id': order['id'],
                        'production_month': order['production_month'],
                        'schno':order['schno'],
                        'dealership':order['dealership'],
                        'model':order['model'],
                        'series_type':order['series_type'],
                        'production_unit': order['production_unit'],
                        'chassis': order['chassis'],

                        'production_date': order['production_date'],
                        'actual_production_date': order['actual_production_date'],
                        'planned_dispatch_date': order['planned_dispatch_date'],
                        
                        'estimated_delay': order['estimated_delay'],

                        'actual_chassis':order['actual_chassis'],
                        'planned_chassis':order['planned_chassis'],
                        'chassis_delay': order['chassis_delay'],
                        
                        'actual_building':order['actual_building'],
                        'planned_building':order['planned_building'],
                        'building_delay': order['building_delay'],
                        
                        'actual_prewire':order['actual_prewire'],
                        'planned_prewire':order['planned_prewire'],
                        'prewire_delay': order['prewire_delay'],

                        'actual_plumbing':order['actual_plumbing'],
                        'planned_plumbing':order['planned_plumbing'],
                        'plumbing_delay': order['plumbing_delay'],


                        'actual_aluminium':order['actual_aluminium'],
                        'planned_aluminium':order['planned_aluminium'],
                        'aluminium_delay': order['aluminium_delay'],
                        
                        'actual_finishing':order['actual_finishing'],
                        'planned_finishing':order['planned_finishing'],
                        'finishing_delay': order['finishing_delay'],

                        'actual_detailing':order['actual_detailing'],
                        'planned_detailing':order['planned_detailing'],
                        'detailing_delay': order['detailing_delay'],

                        'actual_watertest':order['actual_watertest'],
                        'planned_watertest':order['planned_watertest'],
                        'watertest_delay': order['watertest_delay'],

                        'actual_final_qc':order['actual_final_qc'],
                        'planned_final_qc':order['planned_final_qc'],
                        'final_qc_delay': order['final_qc_delay'],

                        'roll_delay': order['chassis_delay'] + order['building_delay'] + order['prewire_delay'] + order['plumbing_delay']+ order['aluminium_delay'] + order['finishing_delay'] + order['detailing_delay'] + order['watertest_delay'] + order['final_qc_delay'],

                    }
                    for order in self.delay_list
                ]

        ########### Get All Exports ############

        if self.category == 'all':
            # print('all exports')
            self.report_type='all'

        ########### Get Chassis Exports ############

        if self.category == 'chassis':
            self.report_type='chassis'

        ########### Get awaiting production data ############

        if self.category == 'building':
            self.report_type='building'

        if self.category == 'prewire':
            self.report_type='prewire'

        if self.category == 'plumbing':
            self.report_type='plumbing'

        if self.category == 'aluminium':
            self.report_type='aluminium'

        if self.category == 'finishing':
            self.report_type='finishing'

        if self.category == 'detailing':
            self.report_type='detailing'

        if self.category == 'watertesting':
            self.report_type='watertesting'

        if self.category == 'finalqc':
            self.report_type='finalqc'


        return self.write_csv()

def convert_date_uniform(date_data=None):
    if date_data:
        if (str(date_data).count('/')>0):
            datetimestring=datetime.strptime(str(parser.parse(str(date_data)).date()),'%Y/%m/%d').strftime('%d-%m-%Y'),
            datetimestring=str(datetimestring).strip("',()/")
            return datetimestring

        elif (str(date_data).count('\\')>0):
            datetimestring=datetime.strptime(str(parser.parse(str(date_data)).date()),'%Y\\%m\\%d').strftime('%d-%m-%Y'),
            datetimestring=str(datetimestring).strip("',()\\")
            return datetimestring

        elif (str(date_data).count('-')>0):
            datetimestring=datetime.strptime(str(parser.parse(str(date_data)).date()),'%Y-%m-%d').strftime('%d-%m-%Y'),
            datetimestring=str(datetimestring).strip("',()")
            return datetimestring
    else:
        return date_data


def getchassisno(order):
    series_type = order.orderseries.series.series_type
    # For Manta Ray add P and For WayFInder Add C to the end of the chassis No.
    # print('Series_Type : ', series_type)
    if (series_type=='PopTops'): 
        return str(order.chassis) + '  P'
    elif (series_type=='Campers'): 
        return str(order.chassis) + '  C'    
    else:
        return str(order.chassis)    

def getdiff(d1=None,d2=None,previous_section=None,order_id=None,production_unit=None,days_reqd=None):
    try:
    
        # actual_date=d1
    
        # planned_date=d2

        # If both the current section date and the previous section date is None return 0 
        if( (d1 is None) and (previous_section is None)):
            diff_count = 0
            return diff_count

        # If the current section date is None and the previous section date is not None take todays date and subtract  
        if( (d1 is None) and (previous_section is not  None)):
            d1 = date.today()
            # return diff_count
        
            # d1 = actual date 
            # d2 = planned date

        # Pass the previous section actual date and the current sections reqd no of days  
        
        # if previous section actual date is there then calculate and
        # make it as the planned date for the current section  

        # if there is an actual date for the section and previous section is also there  
        # current date i.e. d1 is there then 

        if( (d1 is not None) and (previous_section is not None) ):
            d2 = previous_section

        # For sections which are skipped errors occur like plumbing is skipped and actual aluminium is there.
        # Section has actual date but the previous section is not there (skipping)
        if( (d1 is not None) and (previous_section is None) ):
            d2 = d2 

        # Scenario I : Behind Schedule
        # Actual Date > Planned Date 
        if(d1 > d2):
            d1 =datetime.strptime( str(d1),"%Y-%m-%d")
            d2 =datetime.strptime( str(d2),"%Y-%m-%d")
            # days = (d1 - d2)
            # diff = days.days
            # print(order_id,d1,d2,diff)   
            # print(d1,d2,diff)
            diff_count = Capacity.objects.all().filter(day__gte=d2,day__lte=d1,production_unit=production_unit).order_by('day').exclude(capacity=0).count()
            # diff_count = diff_count * -1
            # print(order_id,d1,d2,"Old",diff,'new:',diff_count )
            # Subtract the days_reqd for this section and make it -ve since it is behind schedule
            diff_count = diff_count - days_reqd
            # print(order_id, 'Prod : ', production_unit,' Actual > Planned  : ', d1 , ' : ',d2, ' Diff:', diff_count)
            return int(diff_count * -1)

        # Scenario II : Ahead of Schedule
        # Actual Date < Planned Date 
        if(d1 < d2):
            d1 =datetime.strptime( str(d1),"%Y-%m-%d")
            d2 =datetime.strptime( str(d2),"%Y-%m-%d")
            # days = (d1 - d2)
            # diff = days.days   
            # print(order_id,d1,d2,diff)
            # print(d1,d2,diff)
            diff_count = Capacity.objects.all().filter(day__gte=d1,day__lte=d2,production_unit=production_unit).order_by('day').exclude(capacity=0).count()
            
            diff_count = diff_count - days_reqd

            # diff_count = diff_count 
            # print(order_id,d1,d2,"Old",diff,'new:',diff_count )
            # print(order_id, ' : ', d1 , ' Actual < Planned : ',d2, ' Diff:', diff_count)
            # if(order_id == 16759):
            #     print(order_id, ' : ', d1 , ' Actual < Planned : ',d2, ' Diff:', diff_count)

            return int(diff_count )

        # Scenario III : Both are Equal
        # Actual Date === Planned Date 
        if(d1 == d2):
            # diff = 0
            # print('Equal------------------Dates',diff)
            diff_count=0
            # print(order_id, ' : Equal ', d1 , ' : ',d2, ' Diff:', diff_count)
            return int(diff_count)
         # print('Difference Dates',order_id)

        # return str(diff.days)
    except Exception as e:
        pass 

def get_planned_dates(planned_prod_date=None,order_id=None,production_unit=None,act_production_date=None):
    
    #Calculate the Planned Dispatch Date (Offline Date) 
    # If the Actual Production Date is None then calculate the Dispatch Date based on the Planned Production Date
    # Then the estimated delay should be today minus the calculated dispatch date 

    if(act_production_date is None):
        planned_dates = {}

        if planned_prod_date:

            date_list = Capacity.objects.all().filter(day__gte=planned_prod_date,production_unit=production_unit).order_by('day').exclude(capacity=0).values('day')[:14]

            if(not len(date_list)<14):
                final_date_list = list(reversed(date_list))[0]

                planned_dispatch_date= list(date_list)[13]
                planned_dates['planned_dispatch_date']= planned_dispatch_date['day']

                
                planned_dates['planned_chassis_date'] =None 
                planned_dates['planned_building_date'] = None 
                planned_dates['planned_prewire_date'] =None 
                planned_dates['planned_plumbing_date'] =None
                planned_dates['planned_aluminium_date']=None
                planned_dates['planned_finishing_date'] = None
                planned_dates['planned_detailing_date']=None 
                planned_dates['planned_watertest_date']= None
                # planned_dates['planned_actual_qc_date'] = None 
                planned_dates['planned_final_qc_date'] = None 
                planned_dates['planned_dispatch_date'] = None 
                return planned_dates
        else:
            return planned_dates 

    else:
        date_list = Capacity.objects.all().filter(day__gte=act_production_date,production_unit=production_unit).order_by('day').exclude(capacity=0).values('day')[:14]
        final_date_list = list(reversed(date_list))[0]

        planned_dates = {}
        
        planned_chassis_date= list(date_list)[0]

        planned_dates['planned_chassis_date']= planned_chassis_date['day']
        
        planned_building_date= list(date_list)[1]

        planned_dates['planned_building_date']= planned_building_date['day']

        planned_prewire_date= list(date_list)[2]

        planned_dates['planned_prewire_date']= planned_prewire_date['day']

        planned_plumbing_date= list(date_list)[3]

        planned_dates['planned_plumbing_date']= planned_plumbing_date['day']

        planned_aluminium_date= list(date_list)[4]

        planned_dates['planned_aluminium_date']= planned_aluminium_date['day']

        planned_finishing_date= list(date_list)[5]

        planned_dates['planned_finishing_date']= planned_finishing_date['day']

        planned_detailing_date= list(date_list)[7]

        planned_dates['planned_detailing_date']= planned_detailing_date['day']

        planned_watertest_date= list(date_list)[8]

        planned_dates['planned_watertest_date']= planned_watertest_date['day']
        
        # planned_actual_qc_date= list(date_list)[9]

        # planned_dates['planned_actual_qc_date']= planned_actual_qc_date['day']

        planned_final_qc_date= list(date_list)[9]

        planned_dates['planned_final_qc_date']= planned_final_qc_date['day']

        planned_dispatch_date= list(date_list)[13]

        planned_dates['planned_dispatch_date']= planned_dispatch_date['day']

        return planned_dates
     

class SeriesAvgCSVView(ExportCSVMixin, PermissionRequiredMixin, View):
    permission_required = 'schedule.export_schedule' # Check

    # def get_file_name(self):
    #     return 'Series details with average ball and tare weight' # Check

    def get_complete_file_name(self):
        return 'Series details with average ball and tare weight'

    def get_headers(self, table=None):
        
        headers = [
            'MODEL',
            'SERIES_CODE',
            'SERIES_NAME',
            'TRAVEL_LENGTH (mm)',
            'MAX_EXTERNAL_TRAVEL_HEIGHT (mm)',
            'MAX_INTERNAL_LIVING_HEIGHT (mm)',
            'MAX_TRAVEL_WIDTH (mm)',
            'AVERAGE_TARE_WEIGHT (kg)',
            'AVERAGE_BALL_WEIGHT (kg)',
        ]
        return headers

    def get_rows(self, table=None):

        rows = [
            [
                series.model.name,
                series.code,
                series.name,
                series.length_incl_aframe_mm if series.length_incl_aframe_mm else 0,
                series.length_incl_bumper_mm if series.length_incl_bumper_mm else 0,
                series.height_max_incl_ac_mm if series.height_max_incl_ac_mm else 0,
                series.width_incl_awning_mm if series.width_incl_awning_mm else 0,
                series.avg_tare_weight if series.avg_tare_weight else 0,
                series.avg_ball_weight if series.avg_ball_weight else 0,
            ]
            for series in self.series
            ]

        return rows


    def get(self, request):

        self.series = Series \
            .objects \
            .order_by('model__name', 'name') \
            .select_related(
            'model',
        )
            
        return self.write_csv()