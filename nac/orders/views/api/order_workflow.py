import json

import requests

from allianceutils.views.views import JSONExceptionAPIView
from django.core import serializers
from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse
from django.http import HttpResponse
from django.http.response import HttpResponseBadRequest
from django.http.response import HttpResponseForbidden
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from caravans.models import SKU
from dealerships.models import DealershipUser
from emails.models import EmailTemplate
from newage.egm import update_order_on_egm
from orders.models import FinalizationError
from orders.models import Order
from orders.models import OrderRulePlan
from schedule.models import OrderTransport
from orders.views.api.utils import dropdown_item
from orders.views.api.utils import has_month_empty_production_slots
from orders.views.api.utils import order_data
from orders.views.api.utils import send_email_from_template
from orders.views.api.utils import send_email_on_order_finalization
from production.models import Build,BuildOrder
from production.models import CoilType
from schedule.models import DealerMonthPlanning
from schedule.views.api import ScheduleDashboardAPIView
from schedule.views import api2


class RetrieveOrder(JSONExceptionAPIView):
    permission_required = "orders.view_order"

    default_error_message = 'An error occurred while retrieving the order.'

    def post(self, request):
        try:
            order = Order.objects.get(id=request.data.get('order_id'))
        except Order.DoesNotExist:
            return HttpResponseBadRequest('Order does not exist')

        return JsonResponse(order_data(order, request))


class RequestOrder(JSONExceptionAPIView):
    """
    Called by the sales rep to request an order be approved
    """
    permission_required = "orders.request_order_approval"

    default_error_message = 'An error occurred while requesting approval for the order.'

    def post(self, request):
        order_id = request.data.get('order').get('id')
        order = Order.objects.get(id=order_id)
        if order.get_order_stage() >= Order.STAGE_ORDER_REQUESTED:
            return HttpResponseBadRequest('This order has already been placed.')
        if not order.delivery_date:
            return HttpResponseBadRequest('The order needs to have a valid delivery month selected.')
        if not request.user.has_perm('orders.manual_override') and not has_month_empty_production_slots(order.delivery_date, order.orderseries.production_unit):
            return HttpResponseBadRequest('The selected delivery month is at full capacity. Please select a different delivery month.')
        order.order_rejected = None
        order.order_requested = timezone.now()
        order.save()

        return JsonResponse(order_data(order, request))


class RejectOrder(JSONExceptionAPIView):
    """
    Called by the dealer principal to reject a request for an order be approved
    """
    permission_required = "orders.request_order_approval"

    default_error_message = 'An error occurred while rejecting approval for the order.'

    def post(self, request):
        order_id = request.data.get('order').get('id')
        order = Order.objects.get(id=order_id)
        if order.order_rejected:
            return HttpResponseBadRequest('This order has already been rejected.')
        if order.order_submitted:
            return HttpResponseBadRequest('This order has already been placed.')
        order.order_rejected = timezone.now()
        order.save()

        return JsonResponse(order_data(order, request))

def get_dealer_ordercount_month(dealership_id=None,production_month=None):

        orders_check = Order.objects.all()
            
        orders_check = orders_check.filter(
                order_submitted__isnull=False,
                order_cancelled__isnull=True,
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
            ).exclude(orderseries__production_unit = 2)


        orders_for_month_list = orders_check.filter(build__build_order__production_month=production_month,dealership_id=dealership_id,build__build_order__production_unit=1)

        # print(' Orders Count  : ' , len(orders_for_month_list))

        return len(orders_for_month_list)


class PlaceOrder(JSONExceptionAPIView):
    """
    Called by the dealer principal to approve a requested order
    """
    permission_classes = (IsAuthenticated, )

    default_error_message = 'An error occurred while approving the order.'

    def post(self, request):
        order_id = request.data.get('order').get('id')
        order = Order.objects.get(id=order_id)
        if not request.user.has_perm('orders.approve_order', order):
            return HttpResponseForbidden()
        if not order.order_requested:
            return HttpResponseBadRequest('This order has not yet been submitted')
        if order.order_submitted:
            return HttpResponseBadRequest('This order has already been placed')
        if not order.delivery_date:
            return HttpResponseBadRequest('The order needs to have a valid delivery month selected.')
        if not request.user.has_perm('orders.manual_override') and not has_month_empty_production_slots(order.delivery_date, order.orderseries.production_unit):
            return HttpResponseBadRequest('The selected delivery month is at full capacity. Please select a different delivery month.')
        if order.has_missing_selections:
            return HttpResponseBadRequest('This order cannot be placed while it has incomplete feature selections')
        if order.has_unmet_subject_to():
            return HttpResponseBadRequest('The order cannot be placed while it has Subject To conditions still not met.')

        # print('Series Code :' ,order.get_series_code())
        # # print(' Dealership : ' ,order.dealership.id)
        # orders_check = Order.objects.all()
            
        # orders_check = orders_check.filter(
        #         order_submitted__isnull=False,
        #         order_cancelled__isnull=True,
        #     ).order_by(
        #         'build__build_order__order_number'
        #     ).select_related(
        #         'orderseries',
        #         'orderseries__series',
        #         'orderseries__series__model',
        # 'orderseries__series__model',
        # print('Series Id : ', order.orderseries.series_id)
        # print('Series Code : ', order.get_series_code())
        # print('Model Id : ', order.orderseries.series.model.id)
        # print( 'Month :' , order.delivery_date)

        ############################# DEALER CAPACITY MONTH PLANNING #
        #  The client has temporarily asked to hold this CR -- checking the dealer capacity
        # dealer_order_count = get_dealer_ordercount_month(order.dealership.id,order.delivery_date)
        
        # # print('Existing Order Count  : ', dealer_order_count)

        # # dealer_capacity_allotted = DealerMonthPlanning.objects.filter(dealership_id=order.dealership.id,production_month=order.delivery_date).values_list('capacity_allotted')
        # try:
        #     dealer_capacity_allotted = DealerMonthPlanning.objects.get(production_month=order.delivery_date,dealership_id=order.dealership.id)
        # except DealerMonthPlanning.DoesNotExist as e:
        #     dealer_capacity_allotted=-1
        
        # if dealer_capacity_allotted == -1: 
        #     return HttpResponseBadRequest('Sorry !! Capacity for this dealership for the selected month is not allotted !!')  
         

        # if (dealer_order_count >= dealer_capacity_allotted.capacity_allotted):
        #     return HttpResponseBadRequest('Sorry !! The dealership capacity is full !!')

        
        order.order_submitted = timezone.now()

        if not hasattr(order, 'build'):
            build = Build(
                order=order,
                coil_type=CoilType.objects.first()
            )
            build.save(force_create_build_order=True)    
        else:
            # this is to trigger a (re)create of build_order as pre-existing one might have been removed on finalize cancellation.
            order.build.save()
        
        order.save()

        # print(order.delivery_date)
        try:
            order_list = ScheduleDashboardAPIView.build_order_list(str(order.delivery_date))
        except ImproperlyConfigured as e:
            return HttpResponseBadRequest(str(e))        
    
        
        try:
            ordertrans = OrderTransport.objects.get(order_id = order.id)
        except OrderTransport.DoesNotExist :
            obj = OrderTransport(order_id = order.id)
            obj.save()
        
        if order.customer is not None:
            external_api_call(order.id,request.user.id,'Converted','Order is Placed.')
        

        # external_api_call(order.id,request.user.id,'Converted','Order Placed')
        # order.save()
        if order.customer:
            update_order_on_egm(order)

        # Commented out for the time being - client no longer want order to be finalized - but they may change their mind again later.
        """
        if order.get_special_features_status() == Order.STATUS_NONE:
            # Auto finalize if no special features added
            try:
                order.finalize_order(request.user, True)
            except FinalizationError as e:
                return HttpResponseBadRequest(str(e))
        """
        
        error_response = send_email_from_template(
            order,
            order.customer_manager,
            EmailTemplate.EMAIL_TEMPLATE_ROLE_ORDER_SUBMITTED,
            request,
            'The order has been correctly submitted.',
        )
        
        data = order_data(order, request)
        if error_response:
            data['last_server_error_message'] = error_response.data['message']
            
        return JsonResponse(data)

def external_api_call(order_id,user_id,status_code,reason):
    # url = "https://nac-uat-backend.appretail.io/api/save-order-appretail"
	# url = "https://nac-prod-backend.appretail.io/api/save-order-appretail"
    # url = "https://nac-test-merge.appretail.io/api/save-order-appretail"
    print('inside api call')
    url = "https://nac-dev-merge.appretail.io/api/save-order-appretail"
    
    order=Order.objects.get(id=order_id)

    series_id = order.orderseries.series_id
    model_id = order.orderseries.series.model.id

    print('Series Id : ', series_id)
    print('Series Code : ', order.get_series_code())
    print('Model Id : ', model_id)


    payload = {'order_id': str(order_id),'model_id': str(model_id),'series_id': str(series_id),'order_status': status_code,'user_id': str(user_id),'loss_reason__c': str(reason)}
    
    files = []
    
    headers = { 'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6IjkzZGVmYmNjYmI5MjM3NjE4N2IzYWY5OGNmZDNkMzQ0NTI4ZGU3ZmQxZDdlNWZlNjljODk4NmQxY2VjYjgxZTVkN2RhMmUxODkyMDk1ZTJhIn0.eyJhdWQiOiIyNDciLCJqdGkiOiI5M2RlZmJjY2JiOTIzNzYxODdiM2FmOThjZmQzZDM0NDUyOGRlN2ZkMWQ3ZTVmZTY5Yzg5ODZkMWNlY2I4MWU1ZDdkYTJlMTg5MjA5NWUyYSIsImlhdCI6MTYxNTUzODgyMiwibmJmIjoxNjE1NTM4ODIyLCJleHAiOjE2NDcwNzQ4MjIsInN1YiI6IjU0Iiwic2NvcGVzIjpbXX0.svCAnkdV3OEJqiFv6zIL7PZuHY9jrfYbJgLLz3iSvtTCrZFL6Lgp8s9IO_liH835gSVhvaCTTbnPeunIKUEB-3gN6MheHvIqU-f5iFtS_1V3Vj1w3eFUVFrUHzv2fn4TjstI1RnGT8bTtZKotvKyTsppvU53wWYEfPEmLicZtIRIUt1Ye_3Fywh_WRB6l8LQTf3Rw7BS9xmJyp0tVq5Xm7lYQF_RJ6LZ3fANeyhKcZC53s_GX2mzoSywjJGhLJhwDsSh65dwF5EPgFfRo6qhoqi5VOwVHNnuoe0Pw8ZS5hB9rMRrkt7_m0RJcgvXJ0n--SQjgCVad6FJueqL0hmirMg-aF80MpztpxTn5F1SEjGvlv0JajCG9xfvw8_cMxufcBreWarGmlJTysyWdWPIP_ZzZgESwMLiibQ3K2SXlU_Lot21V0PAlDUgj22XfU4zHhAyvXDRU_a_Xb3CPp2SJHHU4jTlHNP0C5Wf6dWziUmTYU0Yv3JrGtn0Yt779WGOGt2T5P12CD_wzRpsYkieR9ZfgzN2IBCfoVxsHj-LLOceOZSvFUsadJVrOKN0LONMk2QKZdKZK6_o75QuCKcsfntE8KEd0NFrtaO4vra_zrjD50JJtid3WBD7p32tvbu_4kRYYHblYpDAI2hc7dOx_amywjtLwtBZEhxu2bQ5f0Y' }
    # headers = { 'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6IjQ3ZWUwMzZjZGE3ZjdhMjQyYzE1MTBjY2RlODE4MWUyMTlmYmM4YjExYjY2NjgzMmY2ZDllZWY3NmQ2Mjk3YWVmOWQ3NGU0MGYzODcwNGY5In0.eyJhdWQiOiIyMDMiLCJqdGkiOiI0N2VlMDM2Y2RhN2Y3YTI0MmMxNTEwY2NkZTgxODFlMjE5ZmJjOGIxMWI2NjY4MzJmNmQ5ZWVmNzZkNjI5N2FlZjlkNzRlNDBmMzg3MDRmOSIsImlhdCI6MTYxMzgxMzk0MywibmJmIjoxNjEzODEzOTQzLCJleHAiOjE2NDUzNDk5NDMsInN1YiI6IjEwMDUiLCJzY29wZXMiOltdfQ.psdiicakkz3u1blUb4pDlRsqqO4avnVOP1u2OD61iiG15AcDbKxF_34De4S14TV9HJsQ7WBemm2tv2id7_suonnIVwez6HDOQcS29j9iyNojAiPtEJ1PyMLGINmFdXzqTmgH1345kH15u61eZNgk7g6yZ2_PR47i6p1g0F569w6koHr227lBORS1QNF2V0oqvDa9DJABK7F5poEgPtTtwxWqOfPrG9e4OSYbmwzmUgqQuf0_qZ-4kFb9_AOtYPhfYAtC1adAnXWtnwCUGbShgjGyvVhRB21IDqn1hOuyCuCkdRzqNXADXI7FXQNDosqHYoBjhyV53sa_IS0MJqs3QkUgeWxpzK9tTZmtlhDf2NW2DDmU0OPktQrsGqiCchD-jAeV2_aL9MMFXlv7e3030HAUhyjRKO4yQaDRFr5Yye41RxS98liwH10bmNxVysou291fhEEkRuKE3c9Ze71P9xBJ-BfY-FBfCTCB2kcmRmDMlpqaLMOBtKRTHV-yS_9NJANPFiDKsV7K0HNYRXgD21xU-q2aMvP7ex8W7i8C_G8oggCS9MYOpF2DD-jJxqY82lKj3vPiDHO14SxqRGEQhUlpfEg1E9F2tZj2PK0cIl7oX2g8xRyF67boWC3yMyCqZQmZlNZyB8cwAwJ6bFRQc4wtoteAAyX7WsSFEcbIZwU' }
 
    # order=Order.objects.get(id=order_id)
    # print('Series Code:' ,order.get_series_code())

    response = requests.request("POST", url, headers=headers, data = payload, files = files)

    # print(response.text.encode('utf8'))

class CancelOrder(JSONExceptionAPIView):
    """
    Called by the dealer principal to approve a requested order
    """
    permission_classes = (IsAuthenticated, )

    def post(self, request):
        order_id = request.data.get('order').get('id')
        order = Order.objects.get(id=order_id)
        if not request.user.has_perm('orders.cancel_order'):
            return HttpResponseForbidden()
        if order.order_cancelled:
            return HttpResponseBadRequest('This order has already been cancelled')
        if not order.order_submitted:
            return HttpResponseBadRequest('This order has not yet been placed')

        order.cancel_order(request.data.get('cancel_reason'))

        if order.customer is not None:
            external_api_call(order.id,request.user.id,'Cancelled',request.data.get('cancel_reason'))

        if order.customer:
            update_order_on_egm(order)

        return JsonResponse(order_data(order, request))


class FinalizeOrder(JSONExceptionAPIView):
    """
    Called by the dealer principal to finalise a requested order
    """
    permission_classes = (IsAuthenticated, )

    def post(self, request):
        order_id = request.data.get('order').get('id')

        order = Order.objects.get(id=order_id)

        # this is to trigger a (re)create of build_order as pre-existing one might have been removed on finalize cancellation.
        if hasattr(order,'build'):
            order.build.save()
            #print('Build Date ' , order.build.build_date)
        try:
            ordertrans = OrderTransport.objects.get(order_id = order.id)
        except OrderTransport.DoesNotExist :
            obj = OrderTransport(order_id = order.id)
            obj.save()

        if not request.user.has_perm('orders.finalize_order', order) and not request.user.has_perm('orders.lock_order', order):
            return HttpResponseForbidden()

        try:
            order.finalize_order(request.user, False)
        except FinalizationError as e:
            return HttpResponseBadRequest(str(e))

        send_email_on_order_finalization(order, request)

        return JsonResponse(order_data(order, request))


class MassFinalizeOrders(JSONExceptionAPIView):
    """
    Called by dealer principal or anyone with permission order.finalize_order to finalize a number of selected orders
    """
    permission_classes = (IsAuthenticated, )

    def post(self, request):
        # this action is not wrapped in a single transaction as that emails will need to be send for them.
        for order_id in request.data.get('order_list'):
            try:
                order = Order.objects.get(id=order_id)

            except Order.DoesNotExist:
                continue

            if not request.user.has_perm('orders.finalize_order', order):
                continue

            try:
                order.finalize_order(request.user, False)
            except FinalizationError as e:
                # ignore orders cannot be finalized yet or already finalized
                continue

            send_email_on_order_finalization(order, request)

        production_unit = order.orderseries.production_unit

        if production_unit == 2:
            return api2.ScheduleDashboardAPIView.get(api2.ScheduleDashboardAPIView(), request, request.data.get('view_month'))
        else:
            return ScheduleDashboardAPIView.get(ScheduleDashboardAPIView(), request, request.data.get('view_month'))

class CancelFinalize(JSONExceptionAPIView):
    """
    Called to cancel the finalisation of a finalised order
    """
    permission_classes = (IsAuthenticated, )

    def post(self, request):
        order = Order.objects.get(id=request.data.get('order_id'))
        reason = request.data.get('reason')

        if not request.user.has_perm('orders.cancel_finalization'):
            return HttpResponseForbidden()
        if not order.order_finalized_at:
            return HttpResponseBadRequest('This order has not yet been finalised')
        if not reason:
            return HttpResponseBadRequest('A reason needs to be provided for cancelling the finalisation')

        order.cancel_finalization(request.user, reason)

        return JsonResponse(order_data(order, request))


class RulePlanUpload(JSONExceptionAPIView):
    permission_required = "orders.view_or_create_or_modify_order"

    default_error_message = 'An error occurred while uploading plan.'

    def post(self, request):
        data = json.loads(request.data['data'])
        rule_plan = OrderRulePlan()
        rule_plan.order = Order.objects.get(id=data.get('order_id'))
        rule_plan.sku = SKU.objects.get(id=data.get('sku_id'))
        rule_plan.file = request.FILES['file']
        rule_plan.notes = data.get('notes')
        rule_plan.save()
        return JsonResponse({
            'rule_plan_id': rule_plan.id,
        })


class RulePlanRemove(JSONExceptionAPIView):
    permission_required = "orders.view_or_create_or_modify_order"

    default_error_message = 'An error occurred while removing plan.'

    def post(self, request):
        rule_plan = OrderRulePlan.objects.filter(id=request.data['rule_plan_id']).first()
        if rule_plan is None:
            return HttpResponseBadRequest()

        if request.user.has_perm('order.delete_order_rule_plan', rule_plan):
            rule_plan.delete()
            return JsonResponse({})
        else:
            return HttpResponseForbidden()


class CustomerManager(JSONExceptionAPIView):
    """
    Called to update the Customer Manager for the order
    """
    permission_required = "orders.view_or_create_or_modify_order"

    default_error_message = 'An error occurred while setting the customer manager .'

    def post(self, request):
        if (request.data.get('order_id') is None):
            return Response(
                {
                    'customer_manager_list': None
                }
                )

        order_id = request.data.get('order_id')
        order = Order.objects.get(id=order_id)

        customer_manager_id = request.data.get('customer_manager_id')

        if customer_manager_id is None:
            # Return list of potential customer managers
            return Response(
                {
                    'customer_manager_list': [dropdown_item(user) for user in order.dealership.dealershipuser_set.all()]
                }
            )

        # else
        # Update given order with provided customer manager, return new customer manager name

        try:
            customer_manager = DealershipUser.objects.get(id=customer_manager_id)
        except DealershipUser.DoesNotExist:
            return HttpResponseBadRequest()

        order.customer_manager = customer_manager
        order.save()

        return Response(
            {
                'name': order.customer_manager.name
            }
        )


class SalesRep(JSONExceptionAPIView):
    """
    Called to update the Sales Rep for the order
    """
    permission_classes = (IsAuthenticated, )

    default_error_message = 'An error occurred while setting the sales rep.'

    def post(self, request):
        order_id = request.data.get('order_id')
        order = Order.objects.get(id=order_id)

        if not request.user.has_perm('orders.modify_order_sales_rep', order):
            return HttpResponseForbidden()

        sales_rep_id = request.data.get('sales_rep_id')

        if sales_rep_id is None:
            # Return list of potential sales reps
            return JsonResponse(
                {
                    'sales_rep_list': [dropdown_item(user) for user in order.dealership.dealershipuser_set.all()]
                }
            )

        # else
        # Update given order with provided sales_rep, return new sales rep name

        try:
            sales_rep = DealershipUser.objects.get(id=sales_rep_id)
        except DealershipUser.DoesNotExist:
            return HttpResponseBadRequest()

        order.dealer_sales_rep = sales_rep
        order.save()

        return JsonResponse(
            {
                'name': order.dealer_sales_rep.name
            }
        )


class OrderReassign(JSONExceptionAPIView):
    """
    POST processes the reassignment.
    """
    permission_required = "orders.view_or_create_or_modify_order"

    default_error_message = 'An error occurred while reassigning orders.'

    def post(self, request, show_id, dealership_id, manager_id=None):

        orders = Order.objects.filter(show_id=show_id, dealership_id=dealership_id)

        if not manager_id:
            # Return the number of records to be updated
            return JsonResponse({'count': orders.count()})
        # else:

        try:
            manager = DealershipUser.objects.get(id=manager_id)
        except DealershipUser.DoesNotExist:
            return HttpResponseBadRequest("This manager doesn't exist.")

        # Using qs.filter().update(...) doesn't trigger pre/post save signals and won't create an Audit instance
        # https://code.djangoproject.com/ticket/12184
        for order in orders:
            order.customer_manager = manager
            order.save()

        return JsonResponse(
            {
                'message': '{} has been assigned to {} orders.'.format(manager.name, orders.count())
            }
        )
