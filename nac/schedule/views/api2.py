

from collections import OrderedDict
import itertools
import io
from datetime import timedelta
from datetime import date

from dateutil.relativedelta import relativedelta
from dateutil.rrule import MONTHLY
from dateutil.rrule import rrule
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.shortcuts import redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.http import FileResponse
from wsgiref.util import FileWrapper
from django.shortcuts import render_to_response
from django.template.loader import get_template
from django.template.loader import render_to_string
from django.template import Context, RequestContext
from django.views.generic import View
from smtplib import SMTPException
from django.http.response import HttpResponseBadRequest
from django.http.response import HttpResponseForbidden
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.forms import ModelForm
from django.template import loader
from django.shortcuts import render

from django.core.mail import send_mail
from smtplib import SMTPException

from django.core.mail import EmailMessage

from datetime import datetime
from datetime import date
from datetime import timedelta

from allianceutils.views.decorators import gzip_page_ajax
from allianceutils.views.views import JSONExceptionAPIView
from newage.models import Settings
from newage.utils import PrintableMixin
from orders.models import Order
from orders.views.prints import InvoiceView
from caravans.models import SeriesSKU
from caravans.models import SKUCategory
from orders.models import OrderSeries
from orders.models import OrderSeries
from caravans.models import Series
from production.models import Build
from orders.models import OrderDocument
from schedule.models import Capacity
from schedule.models import OrderTransport
from schedule.models import ContractorScheduleExport
from schedule.models import MonthPlanning
from caravans.models import Series
from schedule.models import OrderTransport
from audit.models import Audit
from audit.models import AuditField
from dealerships.models import Dealership

from schedule.serializers import MonthPlanningSerializer
from schedule.utils import assign_build_dates_for_month
from schedule.utils import get_ordinal
from schedule.utils import isoweek_start
from schedule.utils import isoweek_starts


def get_user_permissions(user):
    return {
        'view_schedule_dashboard': user.has_perm('schedule.view_schedule_dashboard'),
        'view_transport_dashboard': user.has_perm('schedule.view_transport_dashboard'),
        'edit_comments_schedule_dashboard': user.has_perm('schedule.edit_comments_schedule_dashboard'),
        'change_schedule_dashboard': user.has_perm('schedule.change_schedule_dashboard'),
        'update_transport_dashboard': user.has_perm('schedule.update_transport_dashboard'),
        'view_schedule_capacity': user.has_perm('schedule.view_schedule_capacity'),
        'change_schedule_capacity': user.has_perm('schedule.change_schedule_capacity'),
        'view_schedule_planner': user.has_perm('schedule.view_schedule_planner'),
        'change_schedule_planner': user.has_perm('schedule.change_schedule_planner'),
        'export_schedule': user.has_perm('schedule.export_schedule'),
        'view_dealer_schedule_dashboard': user.has_perm('schedule.view_dealer_schedule_dashboard'),
        'finalize_order': user.has_perm('orders.finalize_order'),
        'can_hold_caravans': user.has_perm('schedule.can_hold_caravans'),
    }

class ScheduleTransportDashboardMixin(object):

    @classmethod
    def get_order_header_for_month(cls, orders_for_month, month):
        raise NotImplementedError()

    @classmethod
    def get_month_list(cls):
        # Build a list of month for 1 year before to MonthPlanning.MONTH_PLANNING_DEFAULT_LENGTH
        today = timezone.now().date()
        start_month = today.replace(day=1, year=today.year - 1)

        return list(rrule(freq=MONTHLY, dtstart=start_month, count=MonthPlanning.MONTH_PLANNING_DEFAULT_LENGTH+12))

    @classmethod
    def get_special_feature_status(cls, order):
        status = order.get_special_features_status()
        if status == Order.STATUS_PENDING:
            return 'pending'
        if status == Order.STATUS_APPROVED:
            return 'approved'
        if status == Order.STATUS_REJECTED:
            return 'rejected'
        return 'empty'


    @classmethod
    def get_status_string(cls, order):
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

    @classmethod
    def make_list_for_month(cls, orders, month):

        orders_for_month = orders.filter(build__build_order__production_month=month)

        order_list_for_month = [cls.get_order_header_for_month(orders_for_month, month)]

        order_list_for_month += cls.get_order_list_for_month(orders_for_month, month)

        return order_list_for_month

    @classmethod
    def build_order_list(cls, view_month, orders=None):

        if orders is None:
            orders = Order.objects.all()

        orders = orders.filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                orderseries__production_unit=2,
            ).order_by(
                'build__build_order__order_number'
            ).select_related(
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'customer',
                'dealership',
                'build__build_order',
                'build__drafter',
            ).prefetch_related(
                'orderdocument_set',
            )


        current_month = parse_date(view_month).replace(day=1)
        order_list = cls.make_list_for_month(orders, current_month)

        # next_month = (current_month + timedelta(days=31)).replace(day=1)
        # order_list += cls.make_list_for_month(orders, next_month)

        return order_list


class ScheduleDashboardMixin(object):

    @classmethod
    def get_order_header_for_month(cls, orders_for_month, month):
        raise NotImplementedError()

    @classmethod
    def get_month_list(cls):
        # Build a list of month for 1 year before to MonthPlanning.MONTH_PLANNING_DEFAULT_LENGTH
        today = timezone.now().date()
        start_month = today.replace(day=1, year=today.year - 1)

        return list(rrule(freq=MONTHLY, dtstart=start_month, count=MonthPlanning.MONTH_PLANNING_DEFAULT_LENGTH+12))

    @classmethod
    def get_special_feature_status(cls, order):
        status = order.get_special_features_status()
        if status == Order.STATUS_PENDING:
            return 'pending'
        if status == Order.STATUS_APPROVED:
            return 'approved'
        if status == Order.STATUS_REJECTED:
            return 'rejected'
        return 'empty'

    @classmethod
    def get_status_string(cls, order):
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

    @classmethod
    def make_list_for_month(cls, orders, month):

        orders_for_month_list = orders.filter(build__build_order__production_month=month, build__build_order__production_unit=2)

        orders_for_month = orders.filter(build__build_order__production_month=month, build__build_order__production_unit=2)

        order_list_for_month = [cls.get_order_header_for_month(orders_for_month, month)]

        order_list_for_month += cls.get_order_list_for_month(orders_for_month, month)

        return order_list_for_month

    @classmethod
    def build_order_list(cls, view_month, orders=None):

        #################To Check build date empty or not ###################
        if orders is None:
            orders_check = Order.objects.all()

        orders_check = orders_check.filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                orderseries__production_unit=2,
            ).order_by(
                'build__build_order__order_number'
            ).select_related(
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'customer',
                'dealership',
                'build__build_order',
                'build__drafter',
            ).prefetch_related(
                'orderdocument_set',
            )

        view_month1 = date(*map(int, str(view_month).split('-')))
        next_view_month1 = view_month1 + relativedelta(months=1)
        orders_for_month_list_check = orders_check.filter(build__build_order__production_month=view_month1, build__build_order__production_unit=2)
        orders_for_next_month_list_check = orders_check.filter(build__build_order__production_month=next_view_month1, build__build_order__production_unit=2)

        for order in orders_for_month_list_check:
            if not order.build.build_date:
                assign_build_dates_for_month(view_month1, 2)
                break

        for order in orders_for_next_month_list_check:
            if not order.build.build_date:
                assign_build_dates_for_month(next_view_month1, 2)
                break


        ############################# END ########################

        if orders is None:
            orders = Order.objects.all()

        orders = orders.filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                orderseries__production_unit=2,
            ).order_by(
                'build__build_order__order_number'
            ).select_related(
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'customer',
                'dealership',
                'build__build_order',
                'build__drafter',
            ).prefetch_related(
                'orderdocument_set',
            )

        current_month = parse_date(view_month).replace(day=1)
        order_list = cls.make_list_for_month(orders, current_month)

        next_month = (current_month + timedelta(days=31)).replace(day=1)
        order_list += cls.make_list_for_month(orders, next_month)

        return order_list



class DashboardUpdateAPIView(ScheduleDashboardMixin, JSONExceptionAPIView):
    permission_classes = (IsAuthenticated,)

    @method_decorator(gzip_page_ajax)
    def post(self, request):

        ##################### Audit Update ####################

        def enter_to_audit(obj, field_name, new_value):
                    
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')

            aud = Audit(object_id = obj.pk, type = 2, content_type = ContentType.objects.get_for_model(obj), saved_on = datetime.now(), content_repr = obj, user_ip = ip, saved_by = request.user)
            aud.save()

            
            name_in_auditfield = AuditField.objects.filter(name = field_name, audit__object_id = obj.pk, audit__content_type = ContentType.objects.get_for_model(obj)).order_by('-audit__saved_on').first()
            if name_in_auditfield is not None:
                
                old_value = name_in_auditfield.changed_to
                
                audif = AuditField(audit_id = aud.id, name = field_name ,changed_from = old_value, changed_to = new_value)
                audif.save()
            else:
                audif = AuditField(audit_id = aud.id, name = field_name, changed_to = new_value)
                audif.save()

            return None

        if 'lockdown_month' in request.data:
            if not request.user.has_perm('schedule.change_schedule_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")
            return self._lockdown(request.data.get('lockdown_month'), request.data.get('lockdown_number'))

        if 'schedule_comments' in request.data:
            if not request.user.has_perm('schedule.edit_comments_schedule_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")
            order = Order.objects.get(id=request.data.get('order_id'))
            return self._update_comments(order, scheduling_comments=request.data.get('schedule_comments'))

        if 'dealer_comments' in request.data:
            if not request.user.has_perm('schedule.view_dealer_schedule_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")
            order = Order.objects.get(id=request.data.get('order_id'))
            if not request.user.has_perm('orders.modify_order_requested', order):
                return HttpResponseForbidden("You don't have permission to do this.")
            return self._update_comments(order, dealer_comments=request.data.get('dealer_comments'))

        if 'new_position' in request.data:
            if not request.user.has_perm('schedule.change_schedule_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            return self._update_position(
                request.data.get('view_month'),
                request.data.get('order_id'),
                request.data.get('new_month'),
                request.data.get('new_position'),
                request.data.get('previous_order_id'),
                request.data.get('next_order_id')
            )

        if 'production_unit' in request.data:
            if not request.user.has_perm('schedule.change_schedule_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            orders_list = request.data.get('order_list')
            production_unit1 = request.data.get('production_unit')

            if production_unit1 ==1:
                production_unit = 'Caravans'
            else:
                production_unit = 'Pop-Top/Campers'

            for order_id in orders_list:
                orderseries = OrderSeries.objects.get(order_id = order_id)
                enter_to_audit(orderseries, 'production_unit', production_unit)

            return self._update_schedule(
                request.data.get('view_month'),
                request.data.get('order_list'),
                request.data.get('new_schedule_month'),
                request.data.get('new_position_month'),
                request.data.get('production_unit'),
            )

        if 'new_position_month' in request.data:
            if not request.user.has_perm('schedule.change_schedule_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            return self._update_month_position(
                request.data.get('view_month'),
                request.data.get('order_list'),
                request.data.get('new_schedule_month'),
                request.data.get('new_position_month'),
            )


        if 'new_schedule_month' in request.data:
            if not request.user.has_perm('schedule.change_schedule_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            return self._update_month(
                request.data.get('view_month'),
                request.data.get('order_id'),
                request.data.get('new_schedule_month'),
            )
        
        if 'assign_production_dates_for_month' in request.data:
            if not request.user.has_perm('schedule.change_schedule_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            view_month = request.data.get('assign_production_dates_for_month')
            month = parse_date(view_month).replace(day=1)
           
            production_unit = 2
            assign_build_dates_for_month(month, production_unit)

            try:
                order_list = ScheduleDashboardAPIView.build_order_list(view_month)
            except ImproperlyConfigured as e:
                return HttpResponseBadRequest(str(e))

            return Response({'order_list': order_list})

        
        return HttpResponseBadRequest()

    @classmethod
    def _update_comments(cls, order, scheduling_comments=None, dealer_comments=None):
        if dealer_comments is not None:
            order.dealer_comments = dealer_comments
        if scheduling_comments is not None:
            order.scheduling_comments = scheduling_comments
        order.save()
        return Response({})


    @classmethod
    def _lockdown(cls, month, num):
        setting = Settings.get_settings()
        setting.schedule_lockdown_month = month
        setting.schedule_lockdown_number = num
        try:
            setting.save()
        except ValidationError:
            return HttpResponseBadRequest("Invalid Request.")
        return Response({'lockdown_month': month, "lockdown_number": num})

    @classmethod
    def _update_position(cls, view_month, order_id, new_month, new_position, previous_order_id, next_order_id):
        order = Order.objects.get(id=order_id)
        new_month = parse_date(new_month)
        unit = OrderSeries.objects.get(order_id = order_id)

        production_unit = unit.production_unit

        is_move_valid = order.build.move_to_position_in_month(new_position, new_month, production_unit, previous_order_id, next_order_id)

        if not is_move_valid:
            return HttpResponseBadRequest("The information sent does not match what is saved in the database. Please refresh the page.")

        production_unit =2
        view_month1 = date(*map(int, str(view_month).split('-')))
        next_view_month1 = view_month1 + relativedelta(months=1)
        assign_build_dates_for_month(view_month1, production_unit)
        assign_build_dates_for_month(next_view_month1, production_unit)

        try:
            order_list = ScheduleDashboardAPIView.build_order_list(view_month)
        except ImproperlyConfigured as e:
            return HttpResponseBadRequest(str(e))

        return Response({'order_list': order_list})

    @classmethod
    def _update_month_position(cls, view_month, order_id_list, new_schedule_month, new_position):
        new_schedule_month = parse_date(new_schedule_month)
        for order_id in order_id_list:
            order = Order.objects.get(id=order_id)
            unit = OrderSeries.objects.get(order_id = order_id)
            production_unit = unit.production_unit
            order.build.move_to_position_in_month(new_position, new_schedule_month, production_unit)
            new_position += 1

        production_unit =2
        view_month1 = date(*map(int, str(view_month).split('-')))
        next_view_month1 = view_month1 + relativedelta(months=1)
        assign_build_dates_for_month(view_month1, production_unit)
        assign_build_dates_for_month(next_view_month1, production_unit)
        
        new_schedule_month1 = date(*map(int, str(new_schedule_month).split('-')))
        assign_build_dates_for_month(new_schedule_month1, production_unit)

        try:
            order_list = ScheduleDashboardAPIView.build_order_list(str(view_month))
        except ImproperlyConfigured as e:
            return HttpResponseBadRequest(str(e))

        return Response({'order_list': order_list})

    @classmethod
    def _update_month(cls, view_month, order_id, new_schedule_month):
        order = Order.objects.get(id=order_id)
        new_schedule_month = parse_date(new_schedule_month)
        unit = OrderSeries.objects.get(order_id = order_id)
        production_unit = unit.production_unit

        order.build.move_to_position_in_month(-1, new_schedule_month, production_unit)

        production_unit =2
        view_month1 = date(*map(int, str(view_month).split('-')))
        next_view_month1 = view_month1 + relativedelta(months=1)
        assign_build_dates_for_month(view_month1, production_unit)
        assign_build_dates_for_month(next_view_month1, production_unit)
        
        new_schedule_month1 = date(*map(int, str(new_schedule_month).split('-')))
        assign_build_dates_for_month(new_schedule_month1, production_unit)

        try:
            order_list = ScheduleDashboardAPIView.build_order_list(view_month)
        except ImproperlyConfigured as e:
            return HttpResponseBadRequest(str(e))

        return Response({'order_list': order_list})

    @classmethod
    def _update_schedule(cls, view_month, order_list, new_schedule_month, new_position_month, production_unit):
        new_schedule_month = parse_date(new_schedule_month)
        for order_id in order_list:
            order = Order.objects.get(id=order_id)
            production_unit = production_unit

            #update order_series
            change_unit = OrderSeries.objects.filter(order_id = order.id).update(production_unit=production_unit)

            order.build.move_to_position_in_month(new_position_month, new_schedule_month, production_unit)
            new_position_month += 1

        orders = Order.objects.all()
        
        orders = orders.filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month=view_month,
                orderseries__production_unit = 2,
            ).order_by(
                'build__build_order__order_number'
            ).select_related(
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'customer',
                'dealership',
                'build__build_order',
                'build__drafter',
            ).prefetch_related(
                'orderdocument_set',
            )

        new_position_month =1
        production_unit = 2
        month = date(*map(int, view_month.split('-')))
        
        for order in orders:
            order = Order.objects.get(id=order.id)

            order.build.move_to_position_in_month(new_position_month, month, production_unit)
            new_position_month += 1

        month = month + relativedelta(months=1)

        orders2 = Order.objects.all()
        
        orders2 = orders2.filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
                build__build_order__production_month=month,
                orderseries__production_unit = 2,
            ).order_by(
                'build__build_order__order_number'
            ).select_related(
                'orderseries',
                'orderseries__series',
                'orderseries__series__model',
                'customer',
                'dealership',
                'build__build_order',
                'build__drafter',
            ).prefetch_related(
                'orderdocument_set',
            )

        new_position_month =1
        production_unit = 2
        for order in orders2:
            order = Order.objects.get(id=order.id)
            order.build.move_to_position_in_month(new_position_month, month, production_unit)
            new_position_month += 1

        production_unit1 =1
        production_unit2 =2
        view_month1 = date(*map(int, str(view_month).split('-')))
        next_view_month1 = view_month1 + relativedelta(months=1)
        assign_build_dates_for_month(view_month1, production_unit2)
        assign_build_dates_for_month(next_view_month1, production_unit2)
        
        new_schedule_month1 = date(*map(int, str(new_schedule_month).split('-')))
        assign_build_dates_for_month(new_schedule_month1, production_unit1)

        try:
            order_list = ScheduleDashboardAPIView.build_order_list(view_month)
        except ImproperlyConfigured as e:
            return HttpResponseBadRequest(str(e))

        return Response({'order_list': order_list})


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


class DashboardTransportUpdateAPIView(ScheduleTransportDashboardMixin, JSONExceptionAPIView):
    permission_classes = (IsAuthenticated,)


    @method_decorator(gzip_page_ajax)
    def post(self, request):



        ######################## Order Transport Audit Update ##########################

        def enter_to_audit(obj, field_name, new_value):
            
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')

            aud = Audit(object_id = obj.pk, type = 2, content_type = ContentType.objects.get_for_model(obj), saved_on = datetime.now(), content_repr = obj, user_ip = ip, saved_by = request.user)
            aud.save()

            
            name_in_auditfield = AuditField.objects.filter(name = field_name, audit__object_id = obj.pk, audit__content_type = ContentType.objects.get_for_model(obj)).order_by('-audit__saved_on').first()
            if name_in_auditfield is not None:
                
                old_value = name_in_auditfield.changed_to
                
                audif = AuditField(audit_id = aud.id, name = field_name ,changed_from = old_value, changed_to = new_value)
                audif.save()
            else:
                audif = AuditField(audit_id = aud.id, name = field_name, changed_to = new_value)
                audif.save()


            return None

        #################################################################
        order = Order.objects.get(id = request.data.get('order_id'))

        try:
            ordertransport = OrderTransport.objects.get(order_id = order.id)

        except OrderTransport.DoesNotExist :
            obj = OrderTransport(order_id = order.id)
            obj.save()
            ordertransport = OrderTransport.objects.get(order_id = order.id)
        #################################################################

        if 'actual_production_date' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            # ordertransport = OrderTransport.objects.get(order_id = order.id)
            if order.dispatch_date_actual:
                return HttpResponseBadRequest('Dispatched')

            actual_production_date = request.data.get('actual_production_date')
            enter_to_audit(ordertransport, 'actual_production_date', actual_production_date)

            planned_disp_date = request.data.get('planned_disp_date')
            enter_to_audit(order, 'dispatch_date_planned', planned_disp_date)
            
            return self._update_actual_production_date(order.id, actual_production_date1 = actual_production_date, dispatch_date_planned=planned_disp_date)

        if 'prod_comments_from' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            actual_production_comments = str(request.data.get('prod_comments_from'))
            enter_to_audit(ordertransport, 'actual_production_comments', actual_production_comments)

            return self._update_prod_comments(order.id, prod_comments = request.data.get('prod_comments_from'))

        if 'chassis_section' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            chassis_section = request.data.get('chassis_section')

            if order.dispatch_date_actual:
                return HttpResponseBadRequest('Dispatched')

            if ordertransport.actual_production_date:
                enter_to_audit(ordertransport, 'chassis_section', chassis_section)

            return self._update_chassis_section(order.id, chassis_section =request.data.get('chassis_section'))

        if 'chassis_section_comments' in request.data:
            
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            chassis_section_comments=str(request.data.get('chassis_section_comments'))
            enter_to_audit(ordertransport, 'chassis_section_comments', chassis_section_comments)

            return self._update_chassis_section_comments(order.id, chassis_section_comments = request.data.get('chassis_section_comments'))

        if 'building' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            if order.dispatch_date_actual:
                return HttpResponseBadRequest('Dispatched')

            building = request.data.get('building')

            if ordertransport.chassis_section:
                enter_to_audit(ordertransport, 'building', building)

            return self._update_building(order.id, building =request.data.get('building'))

        if 'building_comments' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            building_comments=str(request.data.get('building_comments'))
            enter_to_audit(ordertransport, 'building_comments', building_comments)

            return self._update_building_comments(order.id, building_comments = request.data.get('building_comments'))
        
        if 'prewire_section' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            if order.dispatch_date_actual:
                return HttpResponseBadRequest('Dispatched')

            prewire_section = request.data.get('prewire_section')

            if ordertransport.building:
                enter_to_audit(ordertransport, 'prewire_section', prewire_section)

            return self._update_prewire_section(order.id, prewire_section =request.data.get('prewire_section'))

        if 'prewire_comments' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            prewire_comments=str(request.data.get('prewire_comments'))
            enter_to_audit(ordertransport, 'prewire_comments', prewire_comments)

            return self._update_prewire_comments(order.id, prewire_comments = request.data.get('prewire_comments'))
        
        
        if 'aluminium' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            if order.dispatch_date_actual:
                return HttpResponseBadRequest('Dispatched')

            aluminium = request.data.get('aluminium')

            if ordertransport.prewire_section:
                enter_to_audit(ordertransport, 'aluminium', aluminium)

            return self._update_aluminium(order.id, aluminium =request.data.get('aluminium'))

        if 'aluminium_comments' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            aluminium_comments=str(request.data.get('aluminium_comments'))
            enter_to_audit(ordertransport, 'aluminium_comments', aluminium_comments)

            return self._update_aluminium_comments(order.id, aluminium_comments = request.data.get('aluminium_comments'))

        if 'finishing' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            if order.dispatch_date_actual:
                return HttpResponseBadRequest('Dispatched')
                
            finishing = request.data.get('finishing')

            if ordertransport.aluminium:
                enter_to_audit(ordertransport, 'finishing', finishing)

            return self._update_finishing(order.id, finishing =request.data.get('finishing'))

        if 'finishing_comments' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            finishing_comments=str(request.data.get('finishing_comments'))
            enter_to_audit(ordertransport, 'finishing_comments', finishing_comments)

            return self._update_finishing_comments(order.id, finishing_comments = request.data.get('finishing_comments'))

        if 'detailing_date' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            if order.dispatch_date_actual:
                return HttpResponseBadRequest('Dispatched')

            detailing_date = request.data.get('detailing_date')
            if ordertransport.finishing:
                enter_to_audit(ordertransport, 'detailing_date', detailing_date)

            return self._update_detailing_date(order.id, detailing_date = detailing_date)

        if 'detailing_comments' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            detailing_comments= str(request.data.get('detailing_comments'))
            enter_to_audit(ordertransport, 'detailing_comments', detailing_comments)

            return self._update_detailing_comments(order.id, detailing_comments = request.data.get('detailing_comments'))

        if 'watertest_date' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            if order.dispatch_date_actual:
                return HttpResponseBadRequest('Dispatched')

            watertest_date = request.data.get('watertest_date')
            if ordertransport.detailing_date:
                enter_to_audit(ordertransport, 'watertest_date', watertest_date)

            return self._update_watertest_date(order.id, watertest_date = watertest_date)


        if 'watertest_comments' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            watertest_comments= str(request.data.get('watertest_comments'))
            enter_to_audit(ordertransport, 'watertest_comments', watertest_comments)

            return self._update_watertest_comments(order.id, watertest_comments = request.data.get('watertest_comments'))

        
        if 'actual_qc_date' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            if order.dispatch_date_actual:
                return HttpResponseBadRequest('Dispatched')

            actual_qc_date1 = request.data.get('actual_qc_date')
            build = order.build
            
            if ordertransport.weigh_bridge_date:
                enter_to_audit(build, 'qc_date_actual', actual_qc_date1)

            return self._update_actual_qc_date(order.id, actual_qc_date1 = request.data.get('actual_qc_date'))
       
        if 'qc_comments_from' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            qc_comments= str(request.data.get('qc_comments_from'))
            enter_to_audit(ordertransport, 'qc_comments', qc_comments)

            return self._update_qc_comments(order.id, qc_comments = request.data.get('qc_comments_from'))

        
        if 'final_qc_date' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")
            
            if order.dispatch_date_actual:
                return HttpResponseBadRequest('Dispatched')

            final_qc_date = request.data.get('final_qc_date')

            record_lap1 = Build.objects.get(order_id = order.id)
            
            if record_lap1.qc_date_actual:
                enter_to_audit(ordertransport, 'final_qc_date', final_qc_date)
            try:
                self.sendtestmail('msg',order.id,order.chassis)
                now = datetime.now()
                email_sent_date = datetime.today().date()
                enter_to_audit(ordertransport, 'email_sent', str(email_sent_date))
            except Exception as e:
                print ('Error', e)
                raise
            else:
                pass
            finally:
                today = date.today()
            today = date.today()
            # enter_to_audit(ordertransport, 'Email_Sent', 'Mail Sent')

            return self._update_final_qc_date(order.id, final_qc_date =request.data.get('final_qc_date'))

        if 'final_qc_comments' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            final_qc_comments= str(request.data.get('final_qc_comments'))
            enter_to_audit(ordertransport, 'final_qc_comments', final_qc_comments)

            return self._update_final_qc_comments(order.id, final_qc_comments = request.data.get('final_qc_comments'))

        if 'hold_caravans' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            if not request.user.has_perm('schedule.can_hold_caravans'):
                return HttpResponseForbidden("You don't have permission to do this.")

            hold_caravans=request.data.get('hold_caravans')

            # record_lap1 = OrderTransport.objects.get(order_id = order.id)

            if order.dispatch_date_actual:
                return HttpResponseBadRequest('Order is On Hold Status')
            
            if hold_caravans:
                enter_to_audit(ordertransport, 'hold_caravans', 'On Hold')
            else:
                enter_to_audit(ordertransport, 'hold_caravans', 'Released')
        
            return self._update_hold_caravans(order.id, hold_caravans1 = request.data.get('hold_caravans'))


        if 'actual_dispatch_date' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            actual_dispatch_date1 = request.data.get('actual_dispatch_date')

            if ordertransport.hold_caravans:
                return HttpResponseBadRequest('Order is On Hold Status')
            
            if ordertransport.final_qc_date:
                enter_to_audit(order, 'dispatch_date_actual', actual_dispatch_date1)

            self.sendfinancetestmail('msg',order.id,order.chassis)

            return self._update_actual_dispatch_date(order.id, actual_dispatch_date1 = request.data.get('actual_dispatch_date'))

        if 'dispatch_comments' in request.data:
            if not request.user.has_perm('schedule.update_transport_dashboard'):
                return HttpResponseForbidden("You don't have permission to do this.")

            dispatch_comments=str(request.data.get('dispatch_comments'))
            enter_to_audit(ordertransport, 'dispatch_comments', dispatch_comments)

            return self._update_dispatch_comments(order.id, dispatch_comments = request.data.get('dispatch_comments'))


    @classmethod
    def _update_actual_production_date(cls, orderid, actual_production_date1=None, dispatch_date_planned=None):

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj = OrderTransport.objects.filter(order_id=orderid).update(actual_production_date=actual_production_date1)
            obj1 = Order.objects.filter(id=orderid).update(dispatch_date_planned =  dispatch_date_planned)
        else:
            return HttpResponseBadRequest

        return Response({'msg' : 'Actual producation date updated successfully'})

    @classmethod
    def _update_prod_comments(cls, orderid, prod_comments = None ):

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(actual_production_comments = str(prod_comments))
        else:
            return HttpResponseBadRequest

        return Response({'msg' : 'Production comments updated successfully'})
    @classmethod
    def sendtestmail(cls,msg,order_id,chassis_no):
        
        dealerid = Order.objects.get(id=order_id)
        dname = Dealership.objects.get(id=dealerid.dealership_id)

            # Get Transport Email Id from Dealership
        driver_name=''
        email_id=''    
        # First Set
        if((dealerid.dealership_id == 3) or (dealerid.dealership_id == 13) or (dealerid.dealership_id == 7) or (dealerid.dealership_id == 24) or (dealerid.dealership_id == 26) or (dealerid.dealership_id == 11) or (dealerid.dealership_id == 14 ) or (dealerid.dealership_id == 16)):     
            driver_name='Darren'
            email_id = 'darrenspiteri73@yahoo.com.au'
        
        # Second Set
        if((dealerid.dealership_id == 9) or (dealerid.dealership_id == 5) or (dealerid.dealership_id == 27) or (dealerid.dealership_id == 30) or (dealerid.dealership_id == 31)):     
            driver_name='Gary'
            email_id = 'interstatetowing@outlook.com.au'

        # Third Set
        if((dealerid.dealership_id == 25) or (dealerid.dealership_id == 4) or (dealerid.dealership_id == 12) or (dealerid.dealership_id == 28)):     
            driver_name='Bill'
            email_id = 'billisticlogistics@gmail.com'
        
        if (dealerid.dealership_id == 17):
            return HttpResponseBadRequest('Stock Van')

        msg1 = 'Dear {{driver_name }}, \n'
        msg1 += 'Order No ' + str(order_id) + ' is ready for dispatch to ' + str(dname.name) +  ' vide ID : ' +  str (dealerid.dealership_id) + '\n' + ' Thank You for your reply to xyz@newagecaravans.com.au.'
        
        try:
            subject = 'Van ' + str(chassis_no) + ' ready for delivery to ' + str (dname.name) + "."
            # email_id='velu@qrsolutions.in'
            html_message = loader.render_to_string('email_trans.html',{'driver_name':driver_name,'chassis_no':chassis_no,'dealership_name':dname.name,'email_id':email_id})
            send_mail(subject , msg1 , ' NewAge Caravans  <Annesley.Greig@newagecaravans.com.au>', ['gvelu4@gmail.com','it@newagecaravans.com.au',email_id],html_message=html_message)
            # send_mail(subject , msg1 , ' NewAge Caravans  <Annesley.Greig@newagecaravans.com.au>', ['gvelu4@gmail.com','Suresh.Mathivanan@newagecaravans.com.au'],html_message=html_message)
        
        except SMTPException as e:
            
            print('There was an error sending an email: ', e)
        
        except:
        
            print(' Uncexpected Error')
            raise 
        
        finally:
            print ('')

        
        print ( '' )
    

    @classmethod
    def sendfinancetestmail(cls,msg,order_id,chassis_no):
        print('Entering Mail Part')
        dealerid = Order.objects.get(id=order_id)

        dname = Dealership.objects.get(id=dealerid.dealership_id)
        
        order = Order.objects.get(id=order_id)

        dealer_address = order.dealership.address.address if Dealership \
            .objects \
            .filter(
            id = dealerid.dealership_id,
            address__address__isnull = False,
            ).select_related(
            'address',
            ).exists() else '' 


        dealer_suburb = order.dealership.address.suburb if Dealership \
            .objects \
            .filter(
            id = dealerid.dealership_id,
            address__address__isnull = False,
            address__suburb__isnull = False, 
            ).select_related(
            'address',
            ).exists() else '' 

        customer_name   =  order.customer.name if order.customer else 'STOCK'

        print(customer_name)

        # order = Order.objects.filter(id=order_id)
        print('inside id :', order)
        def get_price(order_sku):
            # When order is finalised, use the wholesale price recorded against the OrderSku object, otherwise the actual sku wholesale price
            if order.get_finalization_status() == Order.STATUS_APPROVED:
                return order_sku.wholesale_price or 0
            return order_sku.sku.wholesale_price or 0

        # Options
        items = [
            {
                'type': 'Option',
                'name': osku.sku.public_description or osku.sku.description,
                'price': get_price(osku),
            } for osku in order.ordersku_set.filter(base_availability_type=SeriesSKU.AVAILABILITY_OPTION)
        ]



        # Upgrades
        items += [
            {
                'type': 'Upgrade' if osku.sku.wholesale_price > 0 else 'Downgrade',
                'name': osku.sku.public_description,
                'price': get_price(osku),
            } for osku in order.ordersku_set.filter(base_availability_type=SeriesSKU.AVAILABILITY_UPGRADE)
        ]

        for special_feature in order.specialfeature_set.all():
            items += [
                {
                    'type': 'Special Feature',
                    'name': special_feature.factory_description or special_feature.customer_description,
                    'price': special_feature.wholesale_price or 0,
                }
            ]

        # Price adjustment
        items += [
            {
                'type': 'Price adjustment',
                'name': order.price_adjustment_wholesale_comment,
                'price': order.price_adjustment_wholesale,
            }
        ]


        context_data = {
            'order': order,
            'date_printed': timezone.now(),
            'items': items,
            'total': (order.orderseries.wholesale_price or 0) + sum([item["price"] for item in items]),
            # 'is_html': is_html,
            # 'is_html': True,
        }
        print('Toal Price : ' ,context_data['total'])
        # return str(context_data['total'])

        total_price = context_data['total']

        # print('order Details',order)

        # Get Transport Email Id from Dealership
        msg1 = 'Dear Finance Team , \n'
        msg1 += 'Order No ' + str(order_id) + ' is ready for dispatch to ' + str(dname.name) +  ' vide ID : ' +  str (dealerid.dealership_id) + '\n' + ' Thank You for your reply to xyz@newagecaravans.com.au.'

        try:
            subject = 'Van ' + str(chassis_no) + ' is Dispatched to ' + str (dname.name) + "."

            html_message = loader.render_to_string('invoice_file.html',{'dealer_name':order.dealership.name,'dispatch_date':timezone.now().date(),'order_id':order.id,'chassis_no':order.chassis,'vin_number':order.build.vin_number,'total_price': total_price})

            send_mail(subject , msg1 , ' NewAge Caravans  <Annesley.Greig@newagecaravans.com.au>', ['gvelu4@gmail.com','accounts@newagecaravans.com.au','it@newagecaravans.com.au'],html_message=html_message)
            # send_mail(subject , msg1 , ' NewAge Caravans  <Annesley.Greig@newagecaravans.com.au>', ['gvelu4@gmail.com'],html_message=html_message)
        
        except SMTPException as e:
            
            print('There was an error sending an email: ', e)
        
        except Exception as e:
        
            print(' Uncexpected Error', e)
            raise 
        
        finally:
            print ( '')

        
        print ( ' ' )
        

    @classmethod
    def _update_email_sent(cls, orderid,email_sent=None):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()
        record_lap1 = OrderTransport.objects.get(order_id= orderid)
        email_sent =  date.today()
        
        if record_lap1.actual_production_date:
            if record_lap is True:
                obj = OrderTransport.objects.filter(order_id = orderid).update(email_sent = email_sent)
            else:
                return HttpResponseBadRequest

            return Response({'msg' : 'Email Sent  Date updated successfully'})

        else:
            return HttpResponseBadRequest('Email is not sent')
    


    @classmethod
    def _update_chassis_section(cls, orderid, chassis_section=None):

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()
        record_lap1 = OrderTransport.objects.get(order_id= orderid)

        if record_lap1.actual_production_date:
            if record_lap is True:
                obj = OrderTransport.objects.filter(order_id = orderid).update(chassis_section = chassis_section)
            else:
                return HttpResponseBadRequest

            return Response({'msg' : 'Chassis section Date updated successfully'})

        else:
            return HttpResponseBadRequest('Production is not Completed')

        
    @classmethod
    def _update_chassis_section_comments(cls, orderid, chassis_section_comments=None):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(chassis_section_comments = str(chassis_section_comments))
            return Response({'msg' : 'Chassis section Comments Updated Successfully'})

        else:
            return HttpResponseBadRequest

    @classmethod
    def _update_building(cls, orderid, building=None):

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()
        record_lap1 = OrderTransport.objects.get(order_id= orderid)

        if record_lap1.chassis_section:
            if record_lap is True:
                obj = OrderTransport.objects.filter(order_id = orderid).update(building = building)
            else:
                return HttpResponseBadRequest

            return Response({'msg' : 'Building Date updated successfully'})
        else:
            return HttpResponseBadRequest('Chassis section is not Completed')
        

    @classmethod
    def _update_building_comments(cls, orderid, building_comments=None):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(building_comments = str(building_comments))
            return Response({'msg' : 'Building Comments Updated Successfully'})

        else:
            return HttpResponseBadRequest

    @classmethod
    def _update_prewire_section(cls, orderid, prewire_section=None):

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()
        record_lap1 = OrderTransport.objects.get(order_id= orderid)

        if record_lap1.building:
            if record_lap is True:
                obj = OrderTransport.objects.filter(order_id = orderid).update(prewire_section = prewire_section)
            else:
                return HttpResponseBadRequest

            return Response({'msg' : 'Prewire Section Date updated successfully'})
        else:
            return HttpResponseBadRequest('Prewire Section Date is not Completed')
        

    @classmethod
    def _update_prewire_comments(cls, orderid, prewire_comments=None):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(prewire_comments = str(prewire_comments))
            return Response({'msg' : 'Prewire Comments Comments Updated Successfully'})

        else:
            return HttpResponseBadRequest

    @classmethod
    def _update_aluminium(cls, orderid, aluminium=None):

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()
        record_lap1 = OrderTransport.objects.get(order_id= orderid)

        if record_lap1.prewire_section:
            if record_lap is True:
                obj = OrderTransport.objects.filter(order_id = orderid).update(aluminium = aluminium)
            else:
                return HttpResponseBadRequest

            return Response({'msg' : 'Aluminium Date updated successfully'})
        else:
            return HttpResponseBadRequest('Building is not Completed')
        

    @classmethod
    def _update_aluminium_comments(cls, orderid, aluminium_comments=None):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(aluminium_comments = str(aluminium_comments))
            return Response({'msg' : 'Aluminium Comments Updated Successfully'})

        else:
            return HttpResponseBadRequest

    @classmethod
    def _update_finishing(cls, orderid, finishing=None):

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()
        record_lap1 = OrderTransport.objects.get(order_id= orderid)

        if record_lap1.aluminium:
            if record_lap is True:
                obj = OrderTransport.objects.filter(order_id = orderid).update(finishing = finishing)
            else:
                return HttpResponseBadRequest

            return Response({'msg' : 'Finishing Date updated successfully'})

        else:
            return HttpResponseBadRequest('Aluminium is not Completed')
        

    @classmethod
    def _update_finishing_comments(cls, orderid, finishing_comments=None):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(finishing_comments = str(finishing_comments))
            return Response({'msg' : 'Finishing Comments Updated Successfully'})

        else:
                return HttpResponseBadRequest

    @classmethod
    def _update_detailing_date(cls, orderid, detailing_date = None): 

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()
        record_lap1 = OrderTransport.objects.get(order_id = orderid)

        if record_lap1.finishing:
        
            if record_lap is True:
                obj1 = OrderTransport.objects.filter(order_id=orderid).update(detailing_date=detailing_date)
            else:
                return HttpResponseBadRequest

            return Response({'msg' : 'Detailing date updated successfully'})
        else:
            return HttpResponseBadRequest('Finishing is not Completed')

    @classmethod
    def _update_detailing_comments(cls, orderid, detailing_comments=None):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(detailing_comments = str(detailing_comments))
            return Response({'msg' : 'Detailing Comments updated successfully'})
        else:
            return HttpResponseBadRequest


    @classmethod
    def _update_watertest_date(cls, orderid, watertest_date = None): 

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()
        record_lap1 = OrderTransport.objects.get(order_id = orderid)

        if record_lap1.detailing_date:    
            if record_lap is True:
                obj1 = OrderTransport.objects.filter(order_id=orderid).update(watertest_date=watertest_date)
            else:
                return HttpResponseBadReques

            return Response({'msg' : 'Water test date updated successfully'})

        else:
            return HttpResponseBadRequest('Detailing Canopy is not Completed')

    @classmethod
    def _update_watertest_comments(cls, orderid, watertest_comments=None):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(watertest_comments = str(watertest_comments))
            return Response({'msg' : 'Water test Comments updated successfully'})
        else:
            return HttpResponseBadRequest

    #weigh_bridge
    @classmethod
    def _update_weigh_bridge_date(cls, orderid, weigh_bridge_date = None): 

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()
        record_lap1 = OrderTransport.objects.get(order_id = orderid)

        if record_lap1.watertest_date:
        
            if record_lap is True:
                obj1 = OrderTransport.objects.filter(order_id=orderid).update(weigh_bridge_date=weigh_bridge_date)
            else:
                return HttpResponseBadRequest

            return Response({'msg' : 'Weigh bridge date updated successfully'})
        else:
            return HttpResponseBadRequest('Water test is not Completed')

    @classmethod
    def _update_weigh_bridge_comments(cls, orderid, weigh_bridge_comments=None):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(weigh_bridge_comments = str(weigh_bridge_comments))
            return Response({'msg' : 'Weigh bridge Comments updated successfully'})
        else:
            return HttpResponseBadRequest

    @classmethod
    def _update_actual_qc_date(cls, orderid, actual_qc_date1=None):

        record_lap = Build.objects.filter(order_id = orderid).exists()
        record_lap1 = OrderTransport.objects.get(order_id = orderid)

        if record_lap1.watertest_date:
            if record_lap is True:
                obj  = Build.objects.filter(order_id = orderid).update(qc_date_actual =  actual_qc_date1)
            else:
                obj = Build(order_id = orderid, qc_date_actual = actual_qc_date1)
                obj.save()

            return Response({'msg' : 'Actual QC date updated successfully'})
        else:
            return HttpResponseBadRequest('Weigh Bridge is not Completed')

    @classmethod
    def _update_qc_comments(cls, orderid, qc_comments = None ):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(qc_comments = str(qc_comments))
            return Response({'msg' : 'QC Comments updated successfully'})

        else:
            return HttpResponseBadRequest

    @classmethod
    def _update_final_qc_date(cls, orderid, final_qc_date=None):

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()
        record_lap1 = Build.objects.get(order_id = orderid)

        if record_lap1.qc_date_actual:
            if record_lap is True:
                obj = OrderTransport.objects.filter(order_id = orderid).update(final_qc_date = final_qc_date,email_sent=final_qc_date)
            else:
                return HttpResponseBadRequest

            return Response({'msg' : 'Final QC Date updated successfully'})

        else:
            return HttpResponseBadRequest('QC is not Completed')

    @classmethod
    def _update_final_qc_comments(cls, orderid, final_qc_comments=None):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(final_qc_comments = str(final_qc_comments))
            return Response({'msg' : 'Final QC Comments Updated Successfully'})

        else:
            return HttpResponseBadRequest

    @classmethod
    def _update_actual_dispatch_date(cls, orderid, actual_dispatch_date1=None):

        # to update avg. in series
        order_item = Order.objects.get(id=orderid)
        if order_item.is_order_converted == 0 and not order_item.customer:
            build_item = Build.objects.get(order_id=order_item.id)
            order_ball_weight = build_item.weight_tow_ball
            order_tare_weight = build_item.weight_tare

            get_series = OrderSeries.objects.get(order_id=order_item.id)
            series_id = get_series.series_id

            series_item = Series.objects.get(id=series_id)
            series_ball_weight = series_item.avg_ball_weight
            series_tare_weight = series_item.avg_tare_weight

            if series_ball_weight:
                if order_ball_weight:
                    avg = (float(series_ball_weight) + float(order_ball_weight))/2
                    item = Series.objects.filter(id=series_id).update(avg_ball_weight=round(avg))
            else:   
                if order_ball_weight:
                    item = Series.objects.filter(id=series_id).update(avg_ball_weight=round(order_ball_weight))

            if series_tare_weight:
                if order_tare_weight:
                    avg = (float(series_tare_weight) + order_tare_weight)/2
                    item = Series.objects.filter(id=series_id).update(avg_tare_weight=round(avg))
            else:
                if order_tare_weight:
                    item = Series.objects.filter(id=series_id).update(avg_tare_weight=round(order_tare_weight))
        ###################################

        record_lap1 = OrderTransport.objects.get(order_id= orderid)

        if not record_lap1.hold_caravans:
            
            if record_lap1.final_qc_date:
                obj  = Order.objects.filter(id=orderid).update(dispatch_date_actual =  actual_dispatch_date1)
                return Response({'msg' : 'Actual dispatech date updated successfully'})
            else:
                return HttpResponseBadRequest('Final QC is not Completed')
        else:
            return HttpResponseBadRequest('Order is On Hold Status')

    @classmethod
    def _update_dispatch_comments(cls, orderid, dispatch_comments=None):
        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()

        if record_lap is True:
            obj  = OrderTransport.objects.filter(order_id=orderid).update(dispatch_comments = str(dispatch_comments))
            return Response({'msg' : 'Dispatch Comments updated successfully'})
        else:
            return HttpResponseBadRequest
        
    @classmethod
    def _update_hold_caravans(cls, orderid, hold_caravans1 = None ):

        record_lap = OrderTransport.objects.filter(order_id= orderid).exists()
        order = Order.objects.get(id = orderid)
        if not order.dispatch_date_actual:
            if record_lap is True:
                obj  = OrderTransport.objects.filter(order_id=orderid).update(hold_caravans = bool(hold_caravans1))
                return Response({'msg' : 'Hold Caravans updated successfully'})
            else:
                return HttpResponseBadRequest

        else:
            return HttpResponseBadRequest('Dispatched')


class ScheduleDashboardAPIView(ScheduleDashboardMixin, JSONExceptionAPIView):

    permission_required = 'schedule.view_schedule_dashboard'

    @classmethod
    def get_order_header_for_month(cls, orders_for_month, month):

        status_summary = {}

        for order in orders_for_month:
            status_string = cls.get_status_string(order)
            status_summary[status_string] = status_summary.get(status_string, 0) + 1

        schedule_month = MonthPlanning.objects.get_or_create(production_month=month, production_unit=2)[0]
        production_unit=2
        capacity = schedule_month.get_capacity(production_unit)
        taken = orders_for_month.filter(order_cancelled__isnull=True).count()

        return {
            'month': month,
            'month_header': month.strftime(settings.FORMAT_DATE_MONTH),
            'capacity': capacity,
            'taken': taken,
            'available': capacity - taken,
            'status_summary': status_summary,
            'signoff_date': schedule_month.sign_off_reminder.strftime(settings.FORMAT_DATE),
        }

    @classmethod
    def get_order_list_for_month(cls, orders_for_month, month):

        destination_months = list(rrule(freq=MONTHLY, dtstart=month - relativedelta(months=1), count=13))

        order_list_for_month = [
            {
                'id': order.id,
                'index': order.build.build_order.order_number,
                'month': month,
                'chassis': str(order.chassis) if order.chassis else '',
                'order_id': '#{}'.format(order.id),
                'model_series': order.custom_series_code or order.orderseries.series.code,
                'special_feature_status': cls.get_special_feature_status(order),
                'dealership': order.dealership.name,
                'customer': order.customer.last_name if order.customer else 'STOCK',
                'schedule_comments': order.scheduling_comments,
                'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                'drafter': ' '.join([word[:1].upper() + '.' for word in order.build.drafter.get_full_name().split(' ')]) if order.build.drafter else '',
                'production_date': order.build.build_date,
                'vin_number': order.build.vin_number,
                'status': cls.get_status_string(order),
                'destination_months': destination_months,
                'planned_qc_date': get_planned_qc(order.build.build_date,10),
            }
            for order in orders_for_month
        ]

        return order_list_for_month

    @method_decorator(gzip_page_ajax)
    def get(self, request, view_month):

        try:
            order_list = self.build_order_list(view_month)
        except ImproperlyConfigured as e:
            return HttpResponseBadRequest(str(e))

        setting = Settings.get_settings()

        return Response(
            {
                'permissions': get_user_permissions(request.user),
                'order_list': order_list,
                'month_list': self.get_month_list(),
                'lockdown_month': setting.schedule_lockdown_month or date(1970,1,1),
                'lockdown_number': setting.schedule_lockdown_number,
            }
        )



def get_planned_qc(product_date, add_days):
    business_days_to_add = add_days
    current_date = product_date
    if product_date:
        while business_days_to_add > 0:
            current_date = current_date + timedelta(days=1)
            weekday = current_date.weekday()
            if weekday >= 5:
                continue
            business_days_to_add = business_days_to_add - 1
        return current_date
    else:
        return 'N/A'
    
def get_status_of_order(orderid):
    today = timezone.now().date()
    order_status = Order.objects.get(id= orderid)
    build_status = Build.objects.get(order_id = orderid)

    try:
        ordertransport_status = OrderTransport.objects.get(order_id = orderid)
    except OrderTransport.DoesNotExist :
        obj = OrderTransport(order_id = orderid)
        obj.save()
        ordertransport_status = OrderTransport.objects.get(order_id = orderid)


    if order_status.dispatch_date_actual:
        return 'Dispatched'
    elif ordertransport_status.final_qc_date:
        return 'Ready For Dispatch'
    elif build_status.qc_date_actual:
        return 'Final QC'
    elif ordertransport_status.weigh_bridge_date:
        return 'QC Canopy'
    elif ordertransport_status.watertest_date:
        return 'Weigh Bridge'
    elif ordertransport_status.detailing_date:
        return 'Water Testing'
    elif ordertransport_status.finishing:
        return 'Detailing'
    elif ordertransport_status.aluminium:
        return 'Finishing'
    elif ordertransport_status.prewire_section:
        return 'Aluminium'
    elif ordertransport_status.building:
        return 'Prewire'
    elif ordertransport_status.chassis_section:
        return 'Building'
    elif ordertransport_status.actual_production_date:
        return 'Chassis'
    else:
        if build_status.build_date and build_status.build_date< today:
            return 'Ready for production'
        else:
            return 'Awaiting Production'
    
def get_capacity_count(act_prod_date=None):

    # Get the query for the Capacity conditions 
    # 1  day greater than the production date from the Capacity table
    # 2  production_unit=1
    # 3  ascending order of day date
    # 4  remove records with capacity =0 ( or select capacity > 0)   
    # 5  finally a lead time of 14 days - to get the 14 days 
    # 6     reverse the list and get the first record from last to get the exact 14th day

    date_list = Capacity.objects.all().filter(day__gte=act_prod_date,production_unit=2).order_by('day').exclude(capacity=0).values('day')[:14]

    final_date_list = list(reversed(date_list))[0]

    return final_date_list['day']
     



class ScheduleTransportDashboardAPIView(ScheduleTransportDashboardMixin, JSONExceptionAPIView):

    permission_required = 'schedule.view_transport_dashboard'

    @classmethod
    def get_order_header_for_month(cls, orders_for_month, month):

        status_summary = {}

        for order in orders_for_month:
            status_string = cls.get_status_string(order)
            status_summary[status_string] = status_summary.get(status_string, 0) + 1

        unit =2 # assign production unit for getting data from capacity

        schedule_month = MonthPlanning.objects.get_or_create(production_month=month, production_unit=2)[0]
        capacity = schedule_month.get_capacity(unit)
        taken = orders_for_month.filter(order_cancelled__isnull=True).count()

        return {
            'month': month,
            'month_header': month.strftime(settings.FORMAT_DATE_MONTH),
            'capacity': capacity,
            'taken': taken,
            'available': capacity - taken,
            'status_summary': status_summary,
            'signoff_date': schedule_month.sign_off_reminder.strftime(settings.FORMAT_DATE),
        }

    
    
    @classmethod
    def get_order_list_for_month(cls, orders_for_month, month):

        destination_months = list(rrule(freq=MONTHLY, dtstart=month - relativedelta(months=1), count=13))

        order_list_for_month = [
            {
                'id': order.id,
                'index': order.build.build_order.order_number,
                'month': month,
                'chassis': str(order.chassis) if order.chassis else '',
                'order_id': '#{}'.format(order.id),
                'model_series': order.custom_series_code or order.orderseries.series.code,
                'special_feature_status': cls.get_special_feature_status(order),
                'dealership': order.dealership.name,
                'customer': order.customer.last_name if order.customer else 'STOCK',
                'schedule_comments': order.scheduling_comments,
                'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                'drafter': ' '.join([word[:1].upper() + '.' for word in order.build.drafter.get_full_name().split(' ')]) if order.build.drafter else '',
                'production_date': order.build.build_date,
                'vin_number': order.build.vin_number,
                'weight_atm': order.build.weight_atm,
                'weight_chassis_gtm': order.build.weight_chassis_gtm,
                'weight_gas_comp': order.build.weight_gas_comp,
                'weight_payload': order.build.weight_payload,
                'weight_tare': order.build.weight_tare,
                'weight_tow_ball': order.build.weight_tow_ball,
                'weight_tyres': order.build.weight_tyres,
                'status': cls.get_status_string(order),
                'destination_months': destination_months,
                'planned_qc_date': order.build.qc_date_planned,
                'watertest_date' : order.ordertransport.watertest_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'watertest_comments' : order.ordertransport.watertest_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'weigh_bridge_date' : order.ordertransport.weigh_bridge_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'weigh_bridge_comments' : order.ordertransport.weigh_bridge_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'detailing_date' : order.ordertransport.detailing_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'detailing_comments' : order.ordertransport.detailing_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'dispatch_comments' : order.ordertransport.dispatch_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'actual_production_date' : order.ordertransport.actual_production_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'prod_comments_from' : order.ordertransport.actual_production_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'qc_comments_from' : order.ordertransport.qc_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'final_qc_date' : order.ordertransport.final_qc_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'final_qc_comments' : order.ordertransport.final_qc_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'actual_qc_date' : order.build.qc_date_actual,
                'chassis_section' : order.ordertransport.chassis_section if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'chassis_section_comments' : order.ordertransport.chassis_section_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'building' : order.ordertransport.building if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'building_comments' : order.ordertransport.building_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'prewire_section' : order.ordertransport.prewire_section if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'prewire_comments' : order.ordertransport.prewire_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'aluminium_date' : order.ordertransport.aluminium if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'aluminium_comments' : order.ordertransport.aluminium_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'finishing' : order.ordertransport.finishing if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'finishing_comments' : order.ordertransport.finishing_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'planned_dispatch_date' : order.dispatch_date_planned,
                'email_sent' : order.ordertransport.email_sent if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'collection_date' : order.ordertransport.collection_date if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'collection_comments' : order.ordertransport.collection_comments if OrderTransport.objects.filter(order_id= order.id).exists() else None,
                'actual_dispatch_date' : order.dispatch_date_actual,
                'hold_caravans' : order.ordertransport.hold_caravans if OrderTransport.objects.filter(order_id= order.id).exists() else False,
                'offline_calc_date' : get_capacity_count(order.build.build_date),
                'order_status' : get_status_of_order(order.id),
            }   
            for order in orders_for_month
        ]

        return order_list_for_month   


    @method_decorator(gzip_page_ajax)
    def get(self, request, view_month):

        try:
            order_list = self.build_order_list(view_month)
        except ImproperlyConfigured as e:
            return HttpResponseBadRequest(str(e))

        setting = Settings.get_settings()

        return Response(
            {
                'permissions': get_user_permissions(request.user),
                'order_list': order_list,
                'month_list': self.get_month_list(),
                'lockdown_month': setting.schedule_lockdown_month or date(1970,1,1),
                'lockdown_number': setting.schedule_lockdown_number,
            }
        )



class ScheduleCapacityAPIView(JSONExceptionAPIView):

    permission_required = 'schedule.view_schedule_capacity'

    @method_decorator(gzip_page_ajax)
    def get(self, request, view_month):

        start_date = parse_date(view_month)
        end_date = (start_date + timedelta(days=6 * 31)).replace(day=1)
        dates_range = (isoweek_start(start_date), isoweek_start(end_date) + timedelta(days=6))

        production_month_starts = {
            m.production_start_date: m.production_month.strftime('%b')
            for m in MonthPlanning.objects.filter(production_start_date__range=dates_range, production_unit=2)
        }

        capacities = {
            c.day: c.capacity
            for c in Capacity.objects.filter(day__range=dates_range, production_unit=2)
        }

        week_list = [
            {
                'start_label': week_date.strftime(settings.FORMAT_DATE),
                'end_label': (week_date + timedelta(days=6)).strftime(settings.FORMAT_DATE),
                'days': [
                    {
                        'day': day.strftime(settings.FORMAT_DATE_ISO),
                        'label': '{day:%a} {day.day}{ord}'.format(day=day, ord=get_ordinal(day.day)),
                        'capacity': capacities.get(day, ''),
                        'month_start': production_month_starts.get(day, ''),
                    }
                    for day in [week_date + timedelta(days=d) for d in range(0, 7)]
                ]
            }
            for week_date in isoweek_starts(start_date, end_date)

        ]

        # Build a list of every 3 months for 3 years, starting 1 year before
        start_month = date(day=1, month=1, year=timezone.now().date().year - 1)
        month_list = list(rrule(freq=MONTHLY, dtstart=start_month, count=12 * 3 // 3, interval=3))

        return Response(
            {
                'permissions': get_user_permissions(request.user),
                'week_list': week_list,
                'month_list': month_list,
            }
        )

    @method_decorator(gzip_page_ajax)
    def post(self, request):

        if not request.user.has_perm('schedule.change_schedule_capacity'):
            return HttpResponseForbidden("You don't have permission to do this.")

        for week in request.data.get('weekList'):
            for week_day in week['days']:
                day = parse_date(week_day['day'])

                if week_day['capacity'] == '' or week_day['capacity'] is None:
                    Capacity.objects.filter(day=day, production_unit=2).delete()
                else:
                    capacity = Capacity.objects.get_restore_or_create(
                        production_unit=2,
                        day=day,
                        defaults={'capacity': week_day['capacity']}
                    )

                    capacity.capacity = week_day['capacity']
                    capacity.save()

        return Response({})


class SchedulePlannerAPIView(JSONExceptionAPIView):

    permission_required = 'schedule.view_schedule_planner'

    @method_decorator(gzip_page_ajax)
    def get(self, request):
        start_date = (datetime.today().date() - relativedelta(months=12)).replace(day=1)
        # start_date = (timezone.now().date().replace(day=1) - timedelta(8)).replace(day=1)  # First day of (First day of current month - 1 day) -> First day of previous month
        end_date = date(
            year=start_date.year + (MonthPlanning.MONTH_PLANNING_DEFAULT_LENGTH // 12),
            month=(start_date.month + MonthPlanning.MONTH_PLANNING_DEFAULT_LENGTH + 1) % 12 + 1,  # Month following (current month + default planning length)
            day=1
        )

        # Create MonthPlannings if they don't already exist
        current_date = start_date
        while current_date < end_date:
            MonthPlanning.objects.update_or_create(production_month=current_date, production_unit=2)
            current_date = date(
                year=current_date.year + current_date.month // 12,
                month=(current_date.month % 12) + 1,
                day=1
            )
        
        month_plannings = MonthPlanning.objects.filter(production_month__range=(start_date, end_date), production_unit=2).order_by('production_month',)


        return Response(
            {
                'permissions': get_user_permissions(request.user),
                'data': MonthPlanningSerializer(month_plannings, many=True).data,
            }
        )

    @method_decorator(gzip_page_ajax)
    def post(self, request):

        if not request.user.has_perm('schedule.change_schedule_planner'):
            return HttpResponseForbidden("You don't have permission to do this.")

        all_data = request.data.get('data')

        try:
            self._check_data_validity(all_data)
        except ValidationError as e:
            return Response(status=400, data=e.messages)
        
        for month_data in all_data:
            planning = MonthPlanning.objects.get(production_month=self._get_date_from_dict(month_data, 'production_month'), production_unit=2)
            planning.production_start_date = self._get_date_from_dict(month_data, 'production_start_date')
            planning.sign_off_reminder = self._get_date_from_dict(month_data, 'sign_off_reminder')
            planning.draft_completion = self._get_date_from_dict(month_data, 'draft_completion')
            planning.closed = month_data.get('closed', False)
            planning.production_unit=2
            planning.save()

        return self.get(request)

    def _check_data_validity(self, all_data):
        if all_data is None:
            raise ValidationError('No data to save.')

        errors = []
        for month_data in all_data:
            production_date = self._get_date_from_dict(month_data, 'production_month')
            if production_date is None:
                errors.append(ValidationError("Some data was missing the production month"))
                break

            dates = OrderedDict([
                ('Draft completion', self._get_date_from_dict(month_data, 'draft_completion')),
                ('Sign off reminder', self._get_date_from_dict(month_data, 'sign_off_reminder')),
            ])

            # Checking that dates exist
            for label, reminder_date in list(dates.items()):
                if reminder_date is None:
                    errors.append(ValidationError('For {}, the {} date cannot be empty.'
                                        .format(production_date.strftime(settings.FORMAT_DATE_MONTH), label)))

            # Checking that dates order are correct
            for (label1, date1), (label2, date2) in itertools.combinations(list(dates.items()), 2):
                if date1 and date2 and date1 > date2:
                    errors.append(ValidationError('For {}, the {} date must be before the {} date.'
                                                  .format(production_date.strftime(settings.FORMAT_DATE_MONTH), label1, label2)))

        if errors:
            raise ValidationError(errors)

    @staticmethod
    def _get_date_from_dict(dic, key):
        if dic.get(key) is None:
            return None
        return datetime.strptime(dic[key].split("T")[0], settings.FORMAT_DATE_ISO).date()
        
        

class ScheduleExportAPIView(JSONExceptionAPIView):

    permission_required = 'schedule.export_schedule'

    @method_decorator(gzip_page_ajax)
    def get(self, request):

        # Build a list of month for 1 year before to MonthPlanning.MONTH_PLANNING_DEFAULT_LENGTH after today
        today = timezone.now().date()
        start_month = today.replace(day=1, year=today.year - 1)

        month_list = list(rrule(freq=MONTHLY, dtstart=start_month, count=MonthPlanning.MONTH_PLANNING_DEFAULT_LENGTH+12))


        return Response(
            {
                'permissions': get_user_permissions(request.user),
                'month_list': month_list,
                'dealer' : [
                    {
                        'id': dealer.id,
                        'name': dealer.name,
                    }
                    for dealer in Dealership.objects.all()
                ],
                'contractor_exports': [
                    {
                        'name': contractor_export.name,
                        'id': contractor_export.id,
                    }
                    for contractor_export in ContractorScheduleExport.objects.all()
                ]
            }
        )


################## New Status Page List ##########################
class ProductionStatusAPIView(JSONExceptionAPIView):

    permission_required = 'schedule.view_transport_dashboard'

    @method_decorator(gzip_page_ajax)
    def get(self, request):

        today = date.today()

        yesterday = datetime.strftime(datetime.now() - timedelta(1), '%Y-%m-%d')

        last_monday = today - timedelta(days=today.weekday())

        month_start = today.replace(day = 1)

        ########## Get awaiting chassis data ############

        chassis_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__chassis_section__isnull = True,
            ordertransport__building__isnull = True,
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

        chassis_count = len(chassis_list)
        ########### Get awaiting Building data ############

        building_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__chassis_section__isnull = False,
            ordertransport__building__isnull = True,
            ordertransport__prewire_section__isnull = True,
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

        prewire_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__chassis_section__isnull = False,
            ordertransport__building__isnull = False,
            ordertransport__prewire_section__isnull = True,
            ordertransport__aluminium__isnull = True,
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

        aluminium_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__chassis_section__isnull = False,
            ordertransport__building__isnull = False,
            ordertransport__prewire_section__isnull = False,
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

        finishing_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__chassis_section__isnull = False,
            ordertransport__building__isnull = False,
            ordertransport__prewire_section__isnull = False,
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

        ########### Detailing Data ##############
        
        detailing_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            orderseries__production_unit=2,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__chassis_section__isnull = False,
            ordertransport__building__isnull = False,
            ordertransport__prewire_section__isnull = False,
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
       
        ########### Water test Data ##############
        
        water_test_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            orderseries__production_unit=2,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__chassis_section__isnull = False,
            ordertransport__building__isnull = False,
            ordertransport__prewire_section__isnull = False,
            ordertransport__aluminium__isnull = False,
            ordertransport__finishing__isnull = False,
            ordertransport__detailing_date__isnull = False,
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

        ########### Weigh bridge Data ##############
        
        weigh_bridge_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            orderseries__production_unit=2,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__chassis_section__isnull = False,
            ordertransport__building__isnull = False,
            ordertransport__prewire_section__isnull = False,
            ordertransport__aluminium__isnull = False,
            ordertransport__finishing__isnull = False,
            ordertransport__detailing_date__isnull = False,
            ordertransport__watertest_date__isnull = False,
            ordertransport__weigh_bridge_date__isnull = True,
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

        

        ########### Get awaiting_qc Data ##############
        
        actual_qc_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__chassis_section__isnull = False,
            ordertransport__building__isnull = False,
            ordertransport__prewire_section__isnull = False,
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

        final_qc_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__detailing_date__isnull = False,
            ordertransport__watertest_date__isnull = False,
            build__qc_date_actual__isnull = False,
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

        ################# Get pending for dispatch data #####################

        ################# Get Ready For Dispatch data #####################
        # self.orders = Order \
        #         .objects \
        #         .filter(
        #         order_submitted__isnull=False,
        #         order_cancelled__isnull=True,
        #         build__build_order__production_month__gte=self.date_from,
        #         build__build_order__production_month__lte=self.date_to,
        #         build__build_order__production_unit=self.production_unit,
        #         ordertransport__actual_production_date__isnull = False,
        #         ordertransport__watertest_date__isnull = False,
        #         ordertransport__weigh_bridge_date__isnull = False,
        #         ordertransport__detailing_date__isnull = False,
        #         build__qc_date_actual__isnull = False,
        #         ordertransport__final_qc_date__isnull =False,
        #         dispatch_date_actual__isnull = True,
        #         ) \
        #         .order_by('build__build_order__production_month', 'build__build_order__order_number') \
        #         .select_related(
        #         'build__build_order',
        #         'orderseries',
        #         'orderseries__series',
        #         'orderseries__series__model',
        #         'show',
        #         'dealership',
        #         'customer',
        #         'build__drafter',
        #     ).prefetch_related('orderdocument_set',)

   
        actual_dispatch_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__watertest_date__isnull = False,
            ordertransport__detailing_date__isnull = False,
            build__qc_date_actual__isnull = False,
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
            'ordertransport',
        ).prefetch_related('orderdocument_set',)

        ################# Email Sent  After Final QC -- Ready For Dispatch data #####################
   
        actual_dispatch_list1 = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__watertest_date__isnull = False,
            ordertransport__detailing_date__isnull = False,
            build__qc_date_actual__isnull = False,
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


         ################# Email Sent Check Collection Date -- Whether 1 day before or after collection date --48 hours #####################
        #    Get Collection Date for order then check whether 1 day before / after (today date) Current Date  
        #    Form a list for such orders and send as green list  
        #    Form a list for orders having collection date greater than tommorow  

        email_sent_green_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit = 2,
            build__build_order__production_month__gte='2019-10-01',
            build__build_order__production_month__lte= today,
            ordertransport__actual_production_date__isnull = False,
            ordertransport__watertest_date__isnull = False,
            ordertransport__detailing_date__isnull = False,
            build__qc_date_actual__isnull = False,
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



        ######################## Today Dispatched #################

        today_dispatched_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            # build__build_order__production_month = today,
            dispatch_date_actual = today,
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

        ######################## Yesterday Dispatched #################

        yesterday_dispatched_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            dispatch_date_actual = yesterday,
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

        ######################## This Week Dispatched #################

        this_week_dispatched_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            dispatch_date_actual__gte = last_monday,
            dispatch_date_actual__lte = today,
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

        ######################## This Month Dispatched #################

        this_month_dispatched_list = Order \
            .objects \
            .filter(
            order_submitted__isnull=False,
            order_cancelled__isnull=True,
            orderseries__production_unit=2,
            dispatch_date_actual__gte = month_start,
            dispatch_date_actual__lte = today,
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


        ############ Getting count ########
        current_user ={'this_user':request.user.get_username(),}

        total_count = {

            'chassis_count' : chassis_list.count(),
            'building_count' : building_list.count(),
            'prewire_count' : prewire_list.count(),
            'aluminium_count' : aluminium_list.count(),
            'finishing_count' : finishing_list.count(),
            'water_test_count' : water_test_list.count(),
            'weigh_bridge_count' : weigh_bridge_list.count(),
            'detailing_count' : detailing_list.count(),
            'actual_qc_count' : actual_qc_list.count(),
            'final_qc_count' : final_qc_list.count(),
            'actual_dispatch_count' : actual_dispatch_list.count(),
            'actual_dispatch_count1' : actual_dispatch_list1.count(),
            'email_sent_green_count' : email_sent_green_list.count(),
            'today_dispatched_count' : today_dispatched_list.count(),
            'yesterday_dispatched_count' : yesterday_dispatched_list.count(),
            'this_week_dispatched_count' : this_week_dispatched_list.count(),
            'this_month_dispatched_count' : this_month_dispatched_list.count(),
        }
        
        #################################
        return Response(
            {
                'permissions': get_user_permissions(request.user),
                'chassis_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in chassis_list
                ],

                'building_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in building_list
                ],

                'prewire_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in prewire_list
                ],

                'aluminium_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in aluminium_list
                ],

                'finishing_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in finishing_list
                ],

                 'detailing_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in detailing_list
                ],

                'water_test_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in water_test_list
                ],

                'weigh_bridge_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in weigh_bridge_list
                ],

               

                'actual_qc_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                        'check_weights': checkweightsfun(order),
                    }
                    for order in actual_qc_list
                ],

                'final_qc_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                        'check_weights' : checkweightsfun(order),
                    }
                    for order in final_qc_list
                ],

                'actual_dispatch_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                        'id': str(order.id),
                    }
                    for order in actual_dispatch_list
                ],

                'actual_dispatch_list1' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                        'id': str(order.id),
                    }
                    for order in actual_dispatch_list1
                ],

                'email_sent_green_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                        'id': str(order.id),
                        'status_green': str(order.chassis) if (get_collection_status(order.id) == 1) else None,  
                        'status_red': str(order.chassis) if (get_collection_status(order.id) == 2) else None,    
                        'status_grey': str(order.chassis) if (get_collection_status(order.id) == 3) else None,  
                    }
                    for order in email_sent_green_list
                ],


                'today_dispatched_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in today_dispatched_list
                ],

                

                'yesterday_dispatched_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in yesterday_dispatched_list
                ],

                'this_week_dispatched_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in this_week_dispatched_list
                ],

                'this_month_dispatched_list' : [
                    {   
                        'production_date': order.build.build_date,
                        'url': '{}#/{}/status'.format(reverse('newage:angular_app', kwargs={'app': 'orders'}), order.id),
                        'chassis': str(order.chassis) if order.chassis else '#%d' %(order.id),
                    }
                    for order in this_month_dispatched_list
                ],

                'total_count' : total_count,
                'current_user':current_user,
            }
        )

def checkweightsfun(order_id):
    if ((order_id.build.weight_tare) and (order_id.build.weight_atm) and (order_id.build.weight_tow_ball) and (order_id.build.weight_chassis_gtm) and (order_id.build.weight_gas_comp) and (order_id.build.weight_payload) ) :
        return True
    else:
        return False 

def get_collection_status(orderid):
    order_status = Order.objects.get(id= orderid)
    build_status = Build.objects.get(order_id = orderid)
    # get date > today 
    ordertrans = OrderTransport.objects.filter(order_id = orderid,collection_date__isnull=False).exists() 
    # print (orderid , ':', ordertrans)
    if ordertrans:
        data1 = OrderTransport.objects.get(order_id = orderid)
        col_date = data1.collection_date  
        # col_date = ordertrans.collection_date
        current_date = date.today()
        yesterday = current_date - timedelta(days=2)
        tommorow  = current_date + timedelta(days=2)
        # print(orderid ,' yest ', yesterday , 'tomm ' , tommorow , ' coll date ' , col_date)

        # if (col_date > yesterday) and (col_date < tommorow)  :

        # Collection Date Passed > 1 day  -- Red == 2 
        if (current_date-col_date).days > 1 :
            # print (orderid,' : ' ,  col_date,' Difference : ',(current_date-col_date).days, 'Red ') 
            return 2

        # Difference between Collection Date and Current Date is 1 or 0 -- Green -- 1    
        if ((current_date-col_date).days == 1) or ((col_date - current_date).days == 1 ) or ((col_date - current_date).days == 0 ) or ((current_date- col_date).days == 0 ):
            # print (orderid, ' : ' , col_date, ' Difference : ',(current_date-col_date).days, 'Green ') 
            return 1

        if (col_date - current_date).days > 1 :
            # print (orderid, ' : ' , col_date, ' Difference : ',(current_date-col_date).days, 'Grey ') 
            return 3
    else:
        return 3
        