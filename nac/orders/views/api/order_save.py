from datetime import datetime
from decimal import Decimal
import json

from allianceutils.views.views import JSONExceptionAPIView
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.http.response import HttpResponseForbidden
from django.utils import timezone
from django.contrib.auth.models import User, Group
from django.contrib.auth import get_user_model


from caravans.models import Rule
from caravans.models import Series
from caravans.models import SeriesSKU
from caravans.models import SKUCategory
from customers.models import AcquisitionSource
from customers.models import Customer
from customers.models import CustomerStatus
from customers.models import SourceOfAwareness
from dealerships.models import Dealership
from dealerships.models import DealershipUser
from dealerships.models import DealershipUserDealership
from emails.models import EmailTemplate
from newage.egm import update_customer_on_egm
from newage.egm import update_order_on_egm
from newage.models import Address
from orders.models import AfterMarketNote
from orders.models import Order
from orders.models import OrderConditions
from orders.models import OrderSeries
from orders.models import OrderShowSpecial
from orders.models import OrderShowSpecialLineItem
from orders.models import OrderSKU
from orders.models import Show
from orders.models import SpecialFeature
from orders.models import OrderNote
# from schedule.models import DealerMonthPlanning
# from orders.views.api.order_workflow import get_dealer_ordercount_month
from orders.serializers import SpecialFeatureSerializer
from orders.views.api.utils import get_available_delivery_months
from orders.views.api.utils import order_data
from orders.views.api.utils import parse_date
from orders.views.api.utils import send_email_from_template
from orders.views.api.order_workflow import external_api_call
from orders.views.api.initial_data import select_sku_effective_date
from production.models import Build
from schedule.models import OrderTransport
from schedule.views.api import ScheduleDashboardAPIView
from schedule.views.api import rebuild_build_order_list


from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.decorators import APIView

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt


# def get_principals(self):
#     """
#     Return a list of DealershipUser that are principals for this dealership
#     Caches results
#     """
#     if not self._principals:
#         self._principals = [dud.dealership_user for dud in DealershipUserDealership.objects.filter(dealership=self, is_principal=True)]
#     return self._principals
# @method_decorator(csrf_exempt, name='dispatch')
class SaveOrderQuote(JSONExceptionAPIView,APIView):
    permission_classes = [IsAuthenticated]
    # permission_required = "orders.view_or_create_or_modify_order"

    default_error_message = 'An error occurred while saving the order.'

    def post(self, request):
        # print('POST Requested ')
        # print(request.data.POST.get['dealership'])
        # print('JSON :', request.body)
        # print('AJAX : ',request.data)
        # print('Entered Quote Section Test')

        data = json.loads(request.body.decode("utf-8"))

        # print('Recvd JSON data', data)

        # print('DealershipUserhip : ' , data['dealership'] )

        # data = json.loads(request.data['data']).get('order')
        # print('First Data',data)
        
        # now suppressing all the permissions for the Quote only
        # print('Data Id : ',data['id'])

        # if data['id'] is not None:
        #     # if not request.user.has_perm('orders.modify_order'):
        #     #     return HttpResponseForbidden()
        #     # else:
        #     #     order = Order.objects.get(id=data['id'])
        #     print('test')
        # else:
                # print('Before Object')
        # print(' Order id ' ,data.get('id'))

        if not(data.get('id') == 'None'):
            print('Checked True as Id')
            if not request.user.has_perm('orders.modify_order'):
                return HttpResponseForbidden()
            else:
                order = Order.objects.get(id=data['id'])


        else:
            # print('No Order Id')
            if not request.user.has_perm('orders.create_order'):
                return HttpResponseForbidden()
            else:
                #print('Before Object')
                order = Order()
                # print('After Object' )
                # print(order ,' #### is as such ### ')


        if order.get_order_stage() == Order.STAGE_CANCELLED:
            raise ValidationError('This order has been cancelled and cannot be modified.')

        # No changes allowed once the order has been finalised, except:
        # - Customer details update (including show)
        # - Converting the order from a stock order to a customer order
        # - Detailed special features update from someone with appropriate permission
        # - Approve special feature from someone with correct permission
        # - Retail price, dealer load price, and trade-in writeback from someone with appropriate permission
        # - if the user has the permission 'orders.modify_order_finalized'
        # - Notes and comments are saved irrespective of the order state
        # if order.get_finalization_status() == Order.STATUS_APPROVED and not request.user.has_perm('orders.modify_order_finalized'):
        #     return self.save_finalized_order(data, request, order)
        
        # print('Before Entering save_order :',order, 'is this ')
        return self.save_order(data, request, order)



    # def save_finalized_order(self, data, request, order):
        data_updated = False

        deals = [dud.dealership_user.id for dud in DealershipUserDealership.objects.filter(dealership=order.dealership, is_principal=True)]

        if request.user.id in deals:
            is_user_principal = True
        else:
            is_user_principal = False

        if self.is_note_updated(data):
            self.update_note_details(data, order)
            data_updated = True

        if request.user.has_perm('orders.modify_special_features'):
            self.update_special_features(request, order, data['special_features'])
            data_updated = True

        if request.user.has_perm('orders.approve_special_features'):
            for special_feature in data['special_features']:
                try:
                    special_feature_object = SpecialFeature.objects.get(id=special_feature.get('id'))
                    special_feature_object.approved = special_feature.get('approved')
                    special_feature_object.reject_reason = special_feature.get('reject_reason') or ''
                    special_feature_object.save()
                except SpecialFeature.DoesNotExist:
                    pass

            order.update_special_features_status(request.user)
            data_updated = True


        if request.user.has_perm('orders.modify_retail_prices_finalized', order):
            order.price_adjustment_retail = data.get('price_adjustments', {}).get('retail') or 0
            
            if order.dispatch_date_actual is None:
                # if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                order.dealer_load = data.get('dealer_load') or 0
                order.trade_in_write_back = data.get('trade_in_write_back') or 0
                order.after_sales_wholesale = data.get('after_sales', {}).get('wholesale') or 0
            else:
                if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                    order.dealer_load = data.get('dealer_load') or 0
                    order.trade_in_write_back = data.get('trade_in_write_back') or 0
                    order.after_sales_wholesale = data.get('after_sales', {}).get('wholesale') or 0
        

            order.after_sales_retail = data.get('after_sales', {}).get('retail') or 0
            order.after_sales_description = data.get('after_sales', {}).get('description') or ''

            order.save()
            data_updated = True



        if request.user.has_perm('orders.modify_order_other_prices', order): 

            if 'price_adjustments' in data:
                if order.dispatch_date_actual is None:
                    order.price_adjustment_wholesale = data.get('price_adjustments', {}).get('wholesale') or 0
                else:
                    if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                        
                        order.price_adjustment_wholesale = data.get('price_adjustments', {}).get('wholesale') or 0

                order.price_adjustment_wholesale_comment = data.get('price_adjustments', {}).get('wholesale_comment') or ''
                if order.price_adjustment_wholesale and not order.price_adjustment_wholesale_comment:
                    raise ValidationError('You need to enter a comment for the wholesale price adjustment.')
                order.save()
                data_updated = True

            if 'trade_in_comment' in data:
                #print ('Trade Data ' ,data.get('trade_in_comment'))
                if order.dispatch_date_actual is None:
                    order.trade_in_comment=data.get('trade_in_comment')
                    order.save()

            if 'trade_in_write_back' in data:
                if order.dispatch_date_actual is None:
                    order.trade_in_write_back = data.get('trade_in_write_back') or 0
                    order.save()
                    data_updated = True
                else:
                    if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                        order.trade_in_write_back = data.get('trade_in_write_back') or 0
                        order.save()
                        data_updated = True

            if 'dealer_load' in data:
                if order.dispatch_date_actual is None:
                    order.dealer_load = data.get('dealer_load') or 0
                    order.save()
                    data_updated = True
                else:
                    if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                        order.dealer_load = data.get('dealer_load') or 0
                        order.save()
                        data_updated = True

            if 'after_sales' in data:
                if order.dispatch_date_actual is None:
                    order.after_sales_wholesale = data.get('after_sales', {}).get('wholesale') or 0
                else:
                    if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                        order.after_sales_wholesale = data.get('after_sales', {}).get('wholesale') or 0
                
                order.after_sales_retail = data.get('after_sales', {}).get('retail') or 0
                order.after_sales_description = data.get('after_sales', {}).get('description') or ''
                order.save()
                data_updated = True

            if 'price_comment' in data :
                order.price_comment = data.get('price_comment')
                order.save()
                data_updated = True
       


        if data.get('update_customer_only'):

            if data.get('order_type') == 'Customer' or order.customer:
                order.customer = self.update_customer(request, data.get('customer'), order.dealer_sales_rep, order.dealership,
                                                      '{order.orderseries.series.model.name} {order.orderseries.series.code}'.format(
                                                          order=order) if hasattr(order, 'orderseries') else None)
                try:
                    order.show = Show.objects.get(id=data.get('show_id', None))
                except Show.DoesNotExist:
                    pass
                order.is_order_converted = data.get('is_order_converted')
                if data.get('order_converted'):
                    order.order_converted = parse_date(data.get('order_converted'))
                order.save()

            if data.get('order_type') == 'Stock':
                order.is_order_converted = False
                order.order_converted = None
                order.show = None
                order.customer = None
                order.save()


            data_updated = True

        if data_updated:
            return JsonResponse(order_data(order, request))

        raise ValidationError('Only comments and note will be saved as order has already been finalised')

    def save_order(self, data, request, order):
        # print('Save Order Entered Order Created Test ')
        if (order.order_submitted or order.order_submitted) and not request.user.has_perm('orders.modify_order_requested', order):
            return JsonResponse(order_data(order, request))

        # if (order.id is None) and data['customer_type'] = 'New':
        #      series_id=None
        # print('Check ', data)
        # print('Checking Series ')
        
        # For New Quote Order / New Customer 
        if (order.id is None)  and data['customer_type'] == 'New':
            series_id = data['series']

        # For New Quote Order / Existing Customer 
        if (order.id is None)  and data['customer_type'] == 'Existing':
            series_id = data['series']
        
        # For Editing Existing Customer 
        if (order.id is None)  and data['customer_type'] == 'Edit':
            series_id= None

        # For Creating New Stock Order
        if (order.id is None)  and data['order_type'] == 'Stock':
            series_id = data['series']

        # For Converting Stock Order to Existing Customer Order 
        if (order.id is not None)  and data['customer_type'] == 'Existing':
            series_id= order.orderseries.series_id

        # For Converting Stock Order to New Customer Order 
        if (order.id is not None)  and data['customer_type'] == 'New':
            series_id=data['series'] 
            order.orderseries.series_id = series_id

        if (order.id is not None)  and data['customer_type'] == 'Edit':
            series_id=data['series'] 
            order.orderseries.series_id = series_id
            # order.orderseries.series_id


      
        dealership_id = data['dealership']

        create_order_series = False
        if series_id is not None:
            if hasattr(order, 'orderseries'):
                # if order.orderseries.series_id != series_id and order.get_order_stage() in [Order.STAGE_ORDER, Order.STAGE_ORDER_FINALIZED]:
                
                print (' ORDER STAGE ! ', order.get_order_stage())

                
                if order.orderseries.series_id != series_id and order.get_order_stage() in [Order.STAGE_ORDER, Order.STAGE_ORDER_FINALIZED]:
                    raise ValidationError('Model and Series cannot be changed once the order is placed.')

                series = Series.objects.get(id=series_id)
                order.orderseries.series = series

                # if not order.get_finalization_status() == Order.STATUS_APPROVED: # once order's finalized, these numbers no longer change
                #     order.orderseries.cost_price = series.cost_price
                #     order.orderseries.wholesale_price = series.wholesale_price
                #     order.orderseries.retail_price = series.retail_price
                #     ###### modified for production unit 2 ###########
                #     order.orderseries.production_unit = series.production_unit
                    ###### modified for production unit 2 ###########
                order.orderseries.save()
                
            else:
                series = Series.objects.get(id=series_id)
                create_order_series = True

        # order.custom_series_name = data.get('custom_series_name') or ''
        # order.custom_series_code = data.get('custom_series_code') or ''

        # print('Before Dealer')
        dealership_id = data['dealership']
        # print('Dealer Process ',dealership_id)
        dealership_user = DealershipUser.objects.filter(id=request.user.id).first()

        if dealership_user is None:  # as in the case of non-dealership users
            dealership = Dealership.objects.filter(pk=dealership_id).first()
        else:
            if dealership_id:
                dealership = dealership_user.dealerships.filter(pk=dealership_id).first()
            else:
                dealership = dealership_user.dealerships.first()

        if dealership is None:
            raise ValidationError("Could not find dealership.")

        order.dealership = dealership

        try:
            order.dealer_sales_rep

        except ObjectDoesNotExist:
            if dealership_user:
                dealer_sales_rep = dealership_user
            else:
                dealer_sales_rep = order.dealership.dealershipuser_set.filter(dealershipuserdealership__is_principal=True).first()

            if dealer_sales_rep is None:
                raise ValidationError('No dealer sales representative selected.')

            order.dealer_sales_rep = dealer_sales_rep

        # print('Create Order Series Value :',create_order_series)
        if create_order_series:
            order.save()
            ###### modified for production unit 2 ###########
            orderseries = OrderSeries.objects.create(order=order, series=series, cost_price=series.cost_price, wholesale_price=series.wholesale_price, retail_price=series.retail_price, production_unit=series.production_unit)
            order.orderseries = orderseries # normally we dont need this but order is cached.
            ###### modified for production unit 2 ###########
        # print('Order Type',data['order_type'])


        if data['order_type'] == 'Customer' or order.customer:
            # print('Entering Customer Vars ')
            if data["customer_type"] == 'Existing':
                # order = Order.objects.get(id=data['id'])
                try:
                    customer=Customer.objects.get (id=data['customer_id'])

                except ObjectDoesNotExist:
                    return JsonResponse({"Error:" : "Invalid Customer Id"  })
                    
                order.customer=customer
                # print('Existing Customer ' , customer )
                
                if data.get('is_order_converted'):
                    # print('IS Order Converted! ')
                    order.is_order_converted = True 
                # data.get('is_order_converted')
                
                if data.get('order_converted'):
                    order.order_converted = parse_date(data.get('order_converted'))
                try:
                    order.show = Show.objects.get(id=data.get('show_id', None))
                except Show.DoesNotExist:
                    pass
                
            # order.is_order_converted = data.get('is_order_converted')
            # if data.get('order_converted'):
            #     order.order_converted = parse_date(data.get('order_converted'))
            # try:
            #     order.show = Show.objects.get(id=data.get('show_id', None))
            # except Show.DoesNotExist:
            #     pass
            # if request.user.has_perm('customers.list_customer'):
            if data["customer_type"] == 'New':
                if order.id:
                    
                    customer = self.update_customer(request, data['customer'], order.dealer_sales_rep, order.dealership,None)
                    order.customer = customer
                    
                    # print('Stock To New Customer ' , customer )
                    
                    if data.get('is_order_converted'):
                        # print('IS Order Converted! ')
                        order.is_order_converted = True 
                    # data.get('is_order_converted')
                    
                    if data.get('order_converted'):
                        order.order_converted = parse_date(data.get('order_converted'))
                    try:
                        order.show = Show.objects.get(id=data.get('show_id', None))
                    except Show.DoesNotExist:
                        pass
                else:
                    customer = self.update_customer(request, data['customer'], order.dealer_sales_rep, order.dealership,None)
                    order.customer = customer

            if data["customer_type"] == 'Edit':
                try:
                    customer=Customer.objects.get (id=data['customer']['id'])
                except ObjectDoesNotExist:
                    return JsonResponse({"Error:" : "Invalid Customer Id"  })

                customer = self.update_customer(request, data['customer'], order.dealer_sales_rep, order.dealership,None)
                # return JsonResponse()
                return JsonResponse({"Success :" : " Customer Info Updated"  })
                # order.customer = customer

        if data['order_type'] == 'Stock':
            # print('Entering Stock Vars')
            order.is_order_converted = False
            order.order_converted = None
            order.show = None
            order.customer = None

        if 'opportunity_no' in data:
            order.appretail_opportunity_no = data.get('opportunity_no')
            # order.save()

        if 'trade_in_comment' in data:
            # print ('Trade Data ' ,data.get('trade_in_comment'))
            if order.dispatch_date_actual is None:
                order.trade_in_comment=data.get('trade_in_comment')
                # order.save()

        # if data.get('price') is not None:
        #     order.price = data.get('price')


        # # if request.user.has_perm('orders.modify_order_other_prices', order):
        #     order.price_comment = data.get('price_comment') or ''
        #     order.dealer_load = data.get('dealer_load') or 0
        #     order.trade_in_write_back = data.get('trade_in_write_back') or 0

        #     if 'after_sales' in data:
        #         order.after_sales_wholesale = data.get('after_sales', {}).get('wholesale') or 0
        #         order.after_sales_retail = data.get('after_sales', {}).get('retail') or 0
        #         order.after_sales_description = data.get('after_sales', {}).get('description') or ''

        #     if 'price_adjustments' in data:
        #         order.price_adjustment_cost = data.get('price_adjustments', {}).get('cost') or 0
        #         order.price_adjustment_wholesale = data.get('price_adjustments', {}).get('wholesale') or 0
        #         order.price_adjustment_wholesale_comment = data.get('price_adjustments', {}).get('wholesale_comment') or ''

        #         if order.price_adjustment_wholesale and not order.price_adjustment_wholesale_comment:
        #             raise ValidationError('You need to enter a comment for the wholesale price adjustment.')

        #         order.price_adjustment_retail = data.get('price_adjustments', {}).get('retail') or 0
    


        # if data.get('weight_estimate_disclaimer', None) is not None:
        #     order.weight_estimate_disclaimer_checked = data.get('weight_estimate_disclaimer')

        # order.custom_tare_weight_kg = data.get('custom_tare_weight')
        # order.custom_ball_weight_kg = data.get('custom_ball_weight')

        order.caravan_details_saved_on = timezone.now()
        order.caravan_details_saved_by = request.user
        order.save()

        if order.customer:
            update_order_on_egm(order)  # Only sync customer orders with eGM

        # if data.get('items', None) is not None:
        #     self.update_order_items(order, data['items'])

        # if data.get('special_features') is not None:
        #     self.update_special_features(request, order, data['special_features'])

        # if data.get('items', None) is None and data.get('special_features') is None and data.get('base_order') is not None:
            # Base order has been selected, but not saved from the feature pages,
            # i.e. there is no items or special features sent along with the save request,
            # but we still need to update according to what has been selected in the base order.
            # base_order = Order.objects.get(id=data.get('base_order'))

            # items = {
            #     item.sku_category_id: {
            #         'id': item.sku_id,
            #         'sku_category': item.sku_category_id,
            #         'availability_type': item.base_availability_type,
            #         'retail_price': item.retail_price,
            #         'wholesale_price': item.wholesale_price,
            #         'cost_price': item.cost_price,
            #     }
            #     for item in base_order.ordersku_set.all()
            # }
            # self.update_order_items(order, items)

            # special_features = SpecialFeatureSerializer(base_order.specialfeature_set.all(), many=True).data
            # self.update_special_features(request, order, special_features)

        # if data.get('show_special') is not None:
        #     self.update_show_special(order, data['show_special'])

        # self.update_note_details(data, order)
        # print('###############################################################')
        # print('Final Order ',order_data(order,request))
        return JsonResponse(order_data(order, request))

    def update_customer(self, request, customer_data, dealer_sales_rep, dealership, series_code):
        customer = None
        # if customer_data.get('id'):
        #     customer = Customer.objects.filter(id=customer_data.get('id')).first()

        if customer_data.__contains__('id')  :
            customer = Customer.objects.get(id= customer_data["id"])

        if not customer:
            print('New Customer ')
            customer = Customer()


        customer.first_name = customer_data['first_name']
        customer.last_name = customer_data['last_name']
        customer.email = customer_data['email']
        customer.phone1 = customer_data['phone1']
        customer.tow_vehicle = customer_data['tow_vehicle']
        # customer.mailing_list = bool(customer_data['mailing_list'])  # When checkbox is unticked mailing_list is present in the data but has value of None


        try:
            
            exist_acquisition_source = AcquisitionSource.objects.filter(name=customer_data['acquisition_source'])

            if len(exist_acquisition_source)>0:
                customer.acquisition_source = exist_acquisition_source[0]
            else:
                new_acquisition_source= AcquisitionSource()
                new_acquisition_source.name = customer_data['acquisition_source']
                new_acquisition_source.save()
                customer.acquisition_source = new_acquisition_source

        except AcquisitionSource.DoesNotExist:
            new_acquisition_source=AcquisitionSource()
            new_acquisition_source.name = customer_data['acquisition_source']
            new_acquisition_source.save()
            customer.acquisition_source = AcquisitionSource.objects.get(id=AcquisitionSource.objects.latest('id'))

            pass


        try:

            exist_source_of_awareness = SourceOfAwareness.objects.filter(name=customer_data['source_of_awareness'])


            if len(exist_source_of_awareness)>0:
                customer.source_of_awareness = exist_source_of_awareness[0]
            else:
                new_source_of_awareness=SourceOfAwareness()
                new_source_of_awareness.name = customer_data['source_of_awareness']
                new_source_of_awareness.save()
                print(new_source_of_awareness)
                customer.source_of_awareness = new_source_of_awareness

        except SourceOfAwareness.DoesNotExist:
            new_source_of_awareness=SourceOfAwareness()
            new_source_of_awareness.name = customer_data['source_of_awareness']
            new_source_of_awareness.save()
            customer.source_of_awareness = SourceOfAwareness.objects.get(id=SourceOfAwareness.objects.latest('id'))

            pass

        if customer_data['partner_name'] is not None:
            customer.partner_name = customer_data['partner_name']

        if customer_data['physical_address']:
            address = Address.create_or_find_matching(customer_data['physical_address']['name'],
                                                      customer_data['physical_address']['address'],
                                                      customer_data['physical_address']['suburb']['name'],
                                                      customer_data['physical_address']['suburb']['post_code']['number'],
                                                      customer_data['physical_address']['suburb']['post_code']['state']['code'])

        
        customer.physical_address = address

  
        customer.appointed_rep = dealer_sales_rep
        customer.appointed_dealer = dealership

        
        try:
            status = CustomerStatus.objects.get(name__iexact='quote')
        except ObjectDoesNotExist:
            status = CustomerStatus()
            status.name = 'Quote'
            status.id = 1
            status.save()

        customer.customer_status = status
        customer.lead_type = Customer.LEAD_TYPE_CUSTOMER
        
        customer.save()
        
        # update_customer_on_egm(customer, series_code)
        return customer
   

    def update_order_items(self, order, skus):
        
        existing = []  # Track selected extras so we can remove ones that have been un-selected

        types_available = (SeriesSKU.AVAILABILITY_SELECTION,
                           SeriesSKU.AVAILABILITY_STANDARD,
                           SeriesSKU.AVAILABILITY_OPTION,
                           SeriesSKU.AVAILABILITY_UPGRADE,)

        order_skus = {osku.sku.sku_category_id: osku for osku in order.ordersku_set.filter(base_availability_type__in=types_available).select_related('sku')}

        for _department_id, sku_object in list(skus.items()):
            print(_department_id, ' : ' , sku_object)

        for _department_id, sku_object in list(skus.items()):
            existing.append(sku_object['id'])

            order_sku = order_skus.get(sku_object['sku_category'])
             
            if not order_sku:
                order_sku = OrderSKU()
            order_sku.order_id = order.id
            order_sku.sku_id = sku_object['id']
            order_sku.base_availability_type = sku_object['availability_type']
            order_sku.retail_price = Decimal(sku_object['retail_price'])
            order_sku.wholesale_price = Decimal(sku_object['wholesale_price'])
            order_sku.cost_price = Decimal(sku_object['cost_price'])
            order_sku.save()
             
        # Remove any extras that are not in the current selection
        OrderSKU.all_objects \
            .filter(order=order)\
            .exclude(sku_id__in=existing) \
            .delete(force=True)

        order.update_missing_selections_status()
        order.save()

    def update_special_features(self, request, order, special_features):
        # Checking that we don't have 2 special features defined for the same department
        errors = []
        category_ids = [special_feature.get('sku_category') for special_feature in special_features]
        duplicates = set([cat_id for cat_id in category_ids if category_ids.count(cat_id) > 1])
        duplicates = [str(department) for department in SKUCategory.objects.filter(id__in=duplicates).exclude(parent=SKUCategory.top())]
        for name in duplicates:
            errors.append(ValidationError('The department {} have several special features defined, please merge them into one.'.format(name)))

        if errors:
            raise ValidationError(errors)

        ids = []  # Track ids, so we can delete stale features
        for special_feature_data in special_features:

            # Filter out all unwanted fields and transforming required fields to the appropriate format
            special_feature_fields = {
                'id': special_feature_data.get('id'),
                'order': order,
                'customer_description': special_feature_data.get('customer_description') or '',
                'retail_price': special_feature_data.get('retail_price'),
                'wholesale_price': special_feature_data.get('wholesale_price'),
                'sku_category_id': special_feature_data.get('sku_category'),
                'factory_description': special_feature_data.get('factory_description') or '',
                'approved': special_feature_data.get('approved'),
                'reject_reason': special_feature_data.get('reject_reason') or '',
            }

            if 'document' not in special_feature_data:
                special_feature_fields.update({'document': None})

            if 'new_document' in special_feature_data:
                special_feature_fields.update({'document': request.FILES.get(str(special_feature_data.get('file_id')))})

            special_feature_id = special_feature_data.get('id')

            if special_feature_id:
                # Using qs.filter().update(...) wouldn't trigger pre/post save signals and wouldn't create an Audit instance
                # https://code.djangoproject.com/ticket/12184
                try:
                    special_feature = SpecialFeature.objects.get(id=special_feature_id)

                    for field, value in list(special_feature_fields.items()):
                        setattr(special_feature, field, value)

                    special_feature.save()
                    ids.append(special_feature_id)
                except SpecialFeature.DoesNotExist:
                    pass
            else:
                feature = SpecialFeature(**special_feature_fields)
                if not feature.is_blank():
                    feature.save()
                    ids.append(feature.id)

        stale = order.specialfeature_set.exclude(id__in=ids)
        stale.delete()

        previous_status = order.get_special_features_status()
        order.update_special_features_status(request.user)
        new_status = order.get_special_features_status()

        if new_status == Order.STATUS_REJECTED and previous_status != new_status:
            reject_reasons = order.specialfeature_set.filter(approved=False).values_list('reject_reason', flat=True)
            send_email_from_template(
                order,
                order.customer_manager,
                EmailTemplate.EMAIL_TEMPLATE_ROLE_SPECIAL_FEATURES_REJECTED,
                request,
                'The special features have been correctly marked as rejected.',
                reject_reason=' ; '.join(reject_reasons),
            )

    def update_show_special(self, order, show_special):
        OrderShowSpecial.objects.filter(order=order).delete()

        if len(show_special.get('applied_rules', [])) == 0:
            return  # No rules were applied for this special, hence no discounts

        order_special = OrderShowSpecial.objects.create(order=order, special_id=show_special['id'])

        for rule_id in show_special['applied_rules']:
            rule = Rule.objects.get(id=rule_id)
            if rule.type == Rule.RULE_PRICE_ADJUSTMENT:
                line_item = OrderShowSpecialLineItem()
                line_item.order_show_special = order_special
                line_item.name = rule.title
                line_item.description = rule.text
                line_item.price_adjustment = rule.price_adjustment
                line_item.save()

    def update_order_conditions(self, order, orderconditions_data):
        try:
            orderconditions = order.orderconditions
        except ObjectDoesNotExist:
            orderconditions = OrderConditions(order=order)

        orderconditions.details = orderconditions_data.get('details', '')
        orderconditions.fulfilled = orderconditions_data.get('fulfilled', False)
        orderconditions.save()

    def update_after_market_note(self, order, aftermarketnote_data):
        try:
            aftermarketnote = order.aftermarketnote
        except ObjectDoesNotExist:
            aftermarketnote = AfterMarketNote(order=order)

        aftermarketnote.note = aftermarketnote_data.get('note', '')
        aftermarketnote.save()

    def is_note_updated(self, data):
        if data.get('orderconditions') or data.get('aftermarketnote') or data.get('trade_in_comment'):
           return True

        return False

    def update_note_details(self, data, order):

        if data.get('orderconditions') is not None:
            self.update_order_conditions(order, data['orderconditions'])

        if data.get('aftermarketnote') is not None:
            self.update_after_market_note(order, data['aftermarketnote'])

        if data.get('trade_in_comment'):
            order.trade_in_comment = data.get('trade_in_comment') or ''

        order.save()
class SaveOrder(JSONExceptionAPIView):
    permission_required = ("orders.view_or_create_or_modify_order")
    default_error_message = 'An error occurred while saving the order.'

    def post(self, request):

        data = json.loads(request.data['data']).get('order')
        

        if data.get('id', None) is not None:
            
            if not request.user.has_perm('orders.modify_order'):
                return HttpResponseForbidden()
            else:
                order = Order.objects.get(id=data['id'])
        else:
            if not request.user.has_perm('orders.create_order'):
                return HttpResponseForbidden()
            else:
                order = Order()

        # data = json.loads(request.data['data']).get('order')
        # print(data['id'])

        # if not(data['id'] == 'None'):
        #     print('Checked True as Id')
        #     if not request.user.has_perm('orders.modify_order'):
        #         return HttpResponseForbidden()
        #     else:
        #         order = Order.objects.get(id=data['id'])


        # else:
        #     # print('No Order Id')
        #     if not request.user.has_perm('orders.create_order'):
        #         return HttpResponseForbidden()
        #     else:
        #         #print('Before Object')
        #         order = Order()
        #         # print('After Object' )
                # print(order ,' #### is as such ### ')


        # data = d['order']

        # if data.get('id', None) is not None:
        #     if not request.user.has_perm('orders.modify_order'):
        #         return HttpResponseForbidden()
        #     else:
        #         order = Order.objects.get(id=data['id'])
        # else:
        #     if not request.user.has_perm('orders.create_order'):
        #         return HttpResponseForbidden()
        #     else:
        #         order = Order()

        if order.get_order_stage() == Order.STAGE_CANCELLED:
            raise ValidationError('This order has been cancelled and cannot be modified.')

        # No changes allowed once the order has been finalised, except:
        # - Customer details update (including show)
        # - Converting the order from a stock order to a customer order
        # - Detailed special features update from someone with appropriate permission
        # - Approve special feature from someone with correct permission
        # - Retail price, dealer load price, and trade-in writeback from someone with appropriate permission
        # - if the user has the permission 'orders.modify_order_finalized'
        # - Notes and comments are saved irrespective of the order state
        if order.get_finalization_status() == Order.STATUS_APPROVED and not request.user.has_perm('orders.modify_order_finalized'):
            return self.save_finalized_order(data, request, order)
        # print('returning save order ')

        return self.save_order(data, request, order)

    def save_finalized_order(self, data, request, order):
        data_updated = False

        deals = [dud.dealership_user.id for dud in DealershipUserDealership.objects.filter(dealership=order.dealership, is_principal=True)]

        if request.user.id in deals:
            is_user_principal = True
        else:
            is_user_principal = False

        if self.is_note_updated(data):
            self.update_note_details(data, order)
            data_updated = True

        if request.user.has_perm('orders.modify_special_features'):
            self.update_special_features(request, order, data['special_features'])
            data_updated = True

        if request.user.has_perm('orders.approve_special_features'):
            for special_feature in data['special_features']:
                try:
                    special_feature_object = SpecialFeature.objects.get(id=special_feature.get('id'))
                    special_feature_object.approved = special_feature.get('approved')
                    special_feature_object.reject_reason = special_feature.get('reject_reason') or ''
                    special_feature_object.save()
                except SpecialFeature.DoesNotExist:
                    pass

            order.update_special_features_status(request.user)
            data_updated = True


        if request.user.has_perm('orders.modify_retail_prices_finalized', order):
            order.price_adjustment_retail = data.get('price_adjustments', {}).get('retail') or 0
            
            if order.dispatch_date_actual is None:
                # if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                order.dealer_load = data.get('dealer_load') or 0
                order.trade_in_write_back = data.get('trade_in_write_back') or 0
                order.after_sales_wholesale = data.get('after_sales', {}).get('wholesale') or 0
            else:
                if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                    order.dealer_load = data.get('dealer_load') or 0
                    order.trade_in_write_back = data.get('trade_in_write_back') or 0
                    order.after_sales_wholesale = data.get('after_sales', {}).get('wholesale') or 0
        

            order.after_sales_retail = data.get('after_sales', {}).get('retail') or 0
            order.after_sales_description = data.get('after_sales', {}).get('description') or ''

            order.save()
            # external_api_call(order.id,request.user.id,'Update','Update')
            data_updated = True


        if request.user.has_perm('orders.modify_order_other_prices', order): 

            if 'price_adjustments' in data:
                if order.dispatch_date_actual is None:
                    order.price_adjustment_wholesale = data.get('price_adjustments', {}).get('wholesale') or 0
                else:
                    if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                        
                        order.price_adjustment_wholesale = data.get('price_adjustments', {}).get('wholesale') or 0

                order.price_adjustment_wholesale_comment = data.get('price_adjustments', {}).get('wholesale_comment') or ''
                if order.price_adjustment_wholesale and not order.price_adjustment_wholesale_comment:
                    raise ValidationError('You need to enter a comment for the wholesale price adjustment.')
                order.save()
                # external_api_call(order.id,request.user.id,'Update','Update')
                data_updated = True

            if 'trade_in_write_back' in data:
                if order.dispatch_date_actual is None:
                    order.trade_in_write_back = data.get('trade_in_write_back') or 0
                    order.save()
                    # external_api_call(order.id,request.user.id,'Update','Update')
                    data_updated = True
                else:
                    if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                        order.trade_in_write_back = data.get('trade_in_write_back') or 0
                        order.save()
                        # external_api_call(order.id,request.user.id,'Update','Update')
                        data_updated = True

            if 'dealer_load' in data:
                if order.dispatch_date_actual is None:
                    order.dealer_load = data.get('dealer_load') or 0
                    order.save()
                    # external_api_call(order.id,request.user.id,'Update','Update')
                    data_updated = True
                else:
                    if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                        order.dealer_load = data.get('dealer_load') or 0
                        order.save()
                        # external_api_call(order.id,request.user.id,'Update','Update')
                        data_updated = True

            if 'after_sales' in data:
                if order.dispatch_date_actual is None:
                    order.after_sales_wholesale = data.get('after_sales', {}).get('wholesale') or 0
                else:
                    if request.user.has_perm('order-status.can_edit_display_totals_after_dispatch') or is_user_principal:
                        order.after_sales_wholesale = data.get('after_sales', {}).get('wholesale') or 0
                
                order.after_sales_retail = data.get('after_sales', {}).get('retail') or 0
                order.after_sales_description = data.get('after_sales', {}).get('description') or ''
                order.save()
                # external_api_call(order.id,request.user.id,'Update','Update')
                data_updated = True

            if 'price_comment' in data :
                order.price_comment = data.get('price_comment')
                order.save()
                # external_api_call(order.id,request.user.id,'Update','Update')
                data_updated = True
       


        if data.get('update_customer_only'):

            if data.get('order_type') == 'Customer' or order.customer:
                order.customer = self.update_customer(request, data.get('customer'), order.dealer_sales_rep, order.dealership,
                                                      '{order.orderseries.series.model.name} {order.orderseries.series.code}'.format(
                                                          order=order) if hasattr(order, 'orderseries') else None)
                try:
                    order.show = Show.objects.get(id=data.get('show_id', None))
                except Show.DoesNotExist:
                    pass
                order.is_order_converted = data.get('is_order_converted')
                if data.get('order_converted'):
                    order.order_converted = parse_date(data.get('order_converted'))
                order.save()
                # external_api_call(order.id,request.user.id,'Update','Update')

            if data.get('order_type') == 'Stock':
                order.is_order_converted = False
                order.order_converted = None
                order.show = None
                order.customer = None
                order.save()
                # external_api_call(order.id,request.user.id,'Update','Update')

            data_updated = True

        if data_updated:
            return JsonResponse(order_data(order, request))

        raise ValidationError('Only comments and note will be saved as order has already been finalised')

    def save_order(self, data, request, order):
        if (order.order_submitted or order.order_submitted) and not request.user.has_perm('orders.modify_order_requested', order):
            return JsonResponse(order_data(order, request))

        series_id = data.get('series', None)
        create_order_series = False
        if series_id is not None:

            if hasattr(order, 'orderseries'):
                # if order.orderseries.series_id != series_id and order.get_order_stage() in [Order.STAGE_ORDER, Order.STAGE_ORDER_FINALIZED]:
                if order.orderseries.series_id != series_id and order.get_order_stage() in [Order.STAGE_ORDER_FINALIZED]:
                    raise ValidationError('Model and Series cannot be changed once the order is Locked.')

                    # raise ValidationError('Model and Series cannot be changed once the order is Placeds.')
                # if order.orderseries.series_id != series_id:
                    

                series = Series.objects.get(id=series_id)
                # print('Before First',order.orderseries.series,'Prod Unit',order.orderseries.production_unit)
                order.orderseries.series = series
                # print('After First',order.orderseries.series,order.orderseries.production_unit)

                if not order.get_finalization_status() == Order.STATUS_APPROVED: # once order's finalized, these numbers no longer change
                    order.orderseries.cost_price = series.cost_price
                    order.orderseries.wholesale_price = series.wholesale_price
                    order.orderseries.retail_price = series.retail_price
                    ###### modified for production unit 2 ###########
                    # order.orderseries.production_unit = series.production_unit
                    ###### modified for production unit 2 ###########
                    #print('Finalization : ',order.orderseries.series,order.orderseries.production_unit)
                order.orderseries.save()
                
            else:
                series = Series.objects.get(id=series_id)
                create_order_series = True

        order.custom_series_name = data.get('custom_series_name') or ''
        order.custom_series_code = data.get('custom_series_code') or ''

        dealership_id = data.get('dealership', None)
        # print('dealership_id :' ,dealership_id)
        dealership_user = DealershipUser.objects.filter(id=request.user.id).first()

        if dealership_user is None:  # as in the case of non-dealership users
            dealership = Dealership.objects.filter(pk=dealership_id).first()
        else:
            if dealership_id:
                dealership = dealership_user.dealerships.filter(pk=dealership_id).first()
            else:
                dealership = dealership_user.dealerships.first()

        if dealership is None:
            raise ValidationError("Could not find dealership.")

        order.dealership = dealership

        # print('Another:',order.dealership)
        
        if data.get('delivery_date'):
            try:
                production_unit = order.orderseries.production_unit
            except OrderSeries.DoesNotExist:
                production_unit = series.production_unit

            requested_delivery_month = datetime.strptime(data.get('delivery_date').split("T")[0], settings.FORMAT_DATE_ISO).date()
            
            if requested_delivery_month != order.delivery_date:
                if requested_delivery_month not in get_available_delivery_months(include_previous_months = False, production_unit = production_unit) and not request.user.has_perm('orders.manual_override'):
                    raise ValidationError('The selected delivery month is not currently available (might be full or closed)')

                # Delaer Capacity Code -- Temporarily Held
                # Check the Dealerships capacity quota
                # Check if the quote is already an order
                # print(request.user.name , 'Permission : ' ,request.user.has_perm('orders.can_override_dealer_capacity'))
                # if request.user.has_perm('orders.can_override_dealer_capacity') is False: 
                #     if order.order_submitted :
                #         test_dealer_quota=self.check_dealer_quota(order,order.dealership.id,requested_delivery_month)
                #         print ('Result :' ,test_dealer_quota)
                #         if test_dealer_quota is False:
                #             raise ValidationError('The quota for this dealership for the desired month is over!!')
                print('Requested Delivery Date : ',requested_delivery_month)
                order.delivery_date = requested_delivery_month
                try:
                    # print('Build : ' , order.build)
                    # print(' Build Order Id : ' , order.build.build_order_id)
                    # if (order.build) and (order.build.build_order_id is None ):
                    #     order.build = None
                    order.build.save(force_create_build_order=True)
                    # print(order.build)
                except Build.DoesNotExist:
                    # print('Build Does Not Exist ! ')
                    pass
                
                # finally:
                #     print(order.delivery_date , 'Finally : ', order.build)
                #     order.build.build_date=order.delivery_date
                #     order.build.save()
                rebuild_build_order_list(requested_delivery_month)

        else:
            order.delivery_date = None

        try:
            order.dealer_sales_rep
        except ObjectDoesNotExist:
            if dealership_user:
                dealer_sales_rep = dealership_user
            else:
                dealer_sales_rep = order.dealership.dealershipuser_set.filter(dealershipuserdealership__is_principal=True).first()

            if dealer_sales_rep is None:
                raise ValidationError('No dealer sales representative selected.')

            order.dealer_sales_rep = dealer_sales_rep

        if create_order_series:
            order.save()
            ###### modified for production unit 2 ###########
            orderseries = OrderSeries.objects.create(order=order, series=series, cost_price=series.cost_price, wholesale_price=series.wholesale_price, retail_price=series.retail_price, production_unit=series.production_unit)
            order.orderseries = orderseries # normally we dont need this but order is cached.
            ###### modified for production unit 2 ###########

        if data.get('order_type') == 'Customer' or order.customer:
            order.is_order_converted = data.get('is_order_converted')
            if data.get('order_converted'):
                order.order_converted = parse_date(data.get('order_converted'))
            try:
                order.show = Show.objects.get(id=data.get('show_id', None))
            except Show.DoesNotExist:
                pass
            if request.user.has_perm('customers.list_customer'):
                customer = self.update_customer(request, data.get('customer'), order.dealer_sales_rep, order.dealership, '{order.orderseries.series.model.name} {order.orderseries.series.code}'.format(order=order) if hasattr(order, 'orderseries') else None)
                order.customer = customer

        if data.get('order_type') == 'Stock':
            order.is_order_converted = False
            order.order_converted = None
            order.show = None
            order.customer = None
            try:
                external_api_call(order.id,request.user.id,'Cancelled','Converted to Dealership Order')
            except Exception as  e:
                print(e)
                pass 
            # -external_api_call(order.id,request.user.id,'Cancelled','Converted to Dealership Order')

        if data.get('price') is not None:
            order.price = data.get('price')


        if request.user.has_perm('orders.modify_order_other_prices', order):
            order.price_comment = data.get('price_comment') or ''
            order.dealer_load = data.get('dealer_load') or 0
            order.trade_in_write_back = data.get('trade_in_write_back') or 0

            if 'after_sales' in data:
                order.after_sales_wholesale = data.get('after_sales', {}).get('wholesale') or 0
                order.after_sales_retail = data.get('after_sales', {}).get('retail') or 0
                order.after_sales_description = data.get('after_sales', {}).get('description') or ''

            if 'price_adjustments' in data:
                order.price_adjustment_cost = data.get('price_adjustments', {}).get('cost') or 0
                order.price_adjustment_wholesale = data.get('price_adjustments', {}).get('wholesale') or 0
                order.price_adjustment_wholesale_comment = data.get('price_adjustments', {}).get('wholesale_comment') or ''

                if order.price_adjustment_wholesale and not order.price_adjustment_wholesale_comment:
                    raise ValidationError('You need to enter a comment for the wholesale price adjustment.')

                order.price_adjustment_retail = data.get('price_adjustments', {}).get('retail') or 0
    


        if data.get('weight_estimate_disclaimer', None) is not None:
            order.weight_estimate_disclaimer_checked = data.get('weight_estimate_disclaimer')

        order.custom_tare_weight_kg = data.get('custom_tare_weight')
        order.custom_ball_weight_kg = data.get('custom_ball_weight')

        order.caravan_details_saved_on = timezone.now()
        order.caravan_details_saved_by = request.user
        order.save()

        if order.customer:
            update_order_on_egm(order)  # Only sync customer orders with eGM

        if data.get('items', None) is not None:
            print('Items Not None ')
            self.update_order_items(order, data['items'])

        if data.get('special_features') is not None:
            self.update_special_features(request, order, data['special_features'])

        if data.get('items', None) is None and data.get('special_features') is None and data.get('base_order') is not None:
            # Base order has been selected, but not saved from the feature pages,
            # i.e. there is no items or special features sent along with the save request,
            # but we still need to update according to what has been selected in the base order.
            base_order = Order.objects.get(id=data.get('base_order'))
            
            print('Check Base Order ')

            items = {
                item.sku_category_id: {
                    'id': item.sku_id,
                    'sku_category': item.sku_category_id,
                    'availability_type': item.base_availability_type,
                    'retail_price': item.retail_price,
                    'wholesale_price': item.wholesale_price,
                    'cost_price': item.cost_price,
                }
                for item in base_order.ordersku_set.all()
            }
            self.update_order_items(order, items)

            special_features = SpecialFeatureSerializer(base_order.specialfeature_set.all(), many=True).data
            self.update_special_features(request, order, special_features)

        if data.get('show_special') is not None:
            self.update_show_special(order, data['show_special'])

        self.update_note_details(data, order)
        try:
            if order.id  :
                print(' Order Id :', order.id , 'User Id ',request.user.id )
                external_api_call(order.id,request.user.id,'Update','Update')
        except Exception as e:
            print('Order Id : ', ' API is not called !' , order.id)
            pass

        # try:
        #     order_list = ScheduleDashboardAPIView.build_order_list(str(order.delivery_date))
        #     # order.build.build_date = order.build.build_order.production_month
        #     # order.build.save()
        # except ImproperlyConfigured as e:
        #     return HttpResponseBadRequest(str(e))

        return JsonResponse(order_data(order, request))

    '''
    def check_dealer_quota(self,order,dealership_id,reqd_production_month):
        print(order.id , ' : ' , dealership_id , ' : ' , reqd_production_month)
        try:
            dealer_capacity_allotted = DealerMonthPlanning.objects.get(production_month=reqd_production_month,dealership_id=dealership_id)
        except DealerMonthPlanning.DoesNotExist as e:
            dealer_capacity_allotted=-1
         
        if dealer_capacity_allotted == -1:
            return HttpResponseBadRequest('Sorry !! Capacity for this dealership for the selected month is not allotted !!')  
        
        dealer_order_count = get_dealer_ordercount_month(dealership_id,reqd_production_month)

        print( 'Capacity Allotted : ' , dealer_capacity_allotted , ' Order Count ' , dealer_order_count)

        if (dealer_order_count >= dealer_capacity_allotted.capacity_allotted):
            return False 
        else:
            return True

    '''
    def update_customer(self, request, customer_data, dealer_sales_rep, dealership, series_code):
        customer = None
        if customer_data.get('id'):
            customer = Customer.objects.filter(id=customer_data.get('id')).first()

        if not customer:
            customer = Customer()

        customer.first_name = customer_data.get('first_name')
        customer.last_name = customer_data.get('last_name')
        customer.email = customer_data.get('email')
        customer.phone1 = customer_data.get('phone1')
        customer.tow_vehicle = customer_data.get('tow_vehicle')
        customer.mailing_list = bool(customer_data.get('mailing_list'))  # When checkbox is unticked mailing_list is present in the data but has value of None

        try:
            customer.acquisition_source = AcquisitionSource.objects.get(id=customer_data.get('acquisition_source'))
        except AcquisitionSource.DoesNotExist:
            pass

        try:
            customer.source_of_awareness = SourceOfAwareness.objects.get(id=customer_data.get('source_of_awareness'))
        except SourceOfAwareness.DoesNotExist:
            pass

        if customer_data.get('partner_name', None) is not None:
            customer.partner_name = customer_data['partner_name']

        if customer_data.get('physical_address', {}):
            address = Address.create_or_find_matching(customer_data['physical_address'].get('name'),
                                                      customer_data['physical_address'].get('address'),
                                                      customer_data['physical_address'].get('suburb', {}).get('name'),
                                                      customer_data['physical_address'].get('suburb', {}).get('post_code', {}).get('number'),
                                                      customer_data['physical_address'].get('suburb', {}).get('post_code', {}).get('state', {}).get('code'))
            customer.physical_address = address

        if customer_data.get('delivery_address') and customer_data.get('delivery_address').get('name', None) is not None:
            address = customer_data['delivery_address']
            delivery_address = Address.create_or_find_matching(
                address.get('name'),
                address.get('address'),
                address.get('suburb', {}).get('name'),
                address.get('suburb', {}).get('post_code', {}).get('number'),
                address.get('suburb', {}).get('post_code', {}).get('state', {}).get('code'))
            customer.delivery_address = delivery_address
            customer.phone_delivery = customer_data.get('phone_delivery')

        if customer_data.get('postal_address') and customer_data.get('postal_address').get('name', None) is not None:
            address = customer_data['postal_address']
            invoice_address = Address.create_or_find_matching(
                address.get('name'),
                address.get('address'),
                address.get('suburb', {}).get('name'),
                address.get('suburb', {}).get('post_code', {}).get('number'),
                address.get('suburb', {}).get('post_code', {}).get('state', {}).get('code'))
            customer.postal_address = invoice_address
            customer.phone_invoice = customer_data.get('phone_invoice')

        customer.appointed_rep = dealer_sales_rep
        customer.appointed_dealer = dealership

        try:
            status = CustomerStatus.objects.get(name__iexact='quote')
        except ObjectDoesNotExist:
            status = CustomerStatus()
            status.name = 'Quote'
            status.id = 1
            status.save()

        customer.customer_status = status
        customer.lead_type = Customer.LEAD_TYPE_CUSTOMER
        customer.save()
        update_customer_on_egm(customer, series_code)
        return customer

    def update_order_items(self, order, skus):
        existing = []  # Track selected extras so we can remove ones that have been un-selected

        types_available = (SeriesSKU.AVAILABILITY_SELECTION,
                           SeriesSKU.AVAILABILITY_STANDARD,
                           SeriesSKU.AVAILABILITY_OPTION,
                           SeriesSKU.AVAILABILITY_UPGRADE,)

        # skus are the items for which we need to find out
        print(' Second Save Change : ', order.delivery_date)
        # requested_delivery_month = order.delivery_date
        selected_date = select_sku_effective_date(order.delivery_date)

        print( 'Sel Date : ', selected_date)

        for _department_id, sku_object in list(skus.items()):
            print( _department_id , ' = ' , sku_object['id'])

        order_skus = {osku.sku.sku_category_id: osku for osku in order.ordersku_set.filter(base_availability_type__in=types_available).select_related('sku')}

        for _department_id, sku_object in list(skus.items()):
            existing.append(sku_object['id'])

            order_sku = order_skus.get(sku_object['sku_category'])
            try:

                if not order_sku:
                    order_sku = OrderSKU()
                order_sku.order_id = order.id
                order_sku.sku_id = sku_object['id']
                order_sku.base_availability_type = sku_object['availability_type']
                
                if sku_object['retail_price'] is None:
                    sku_object['retail_price']=str('0.00')
                if sku_object['wholesale_price'] is None:
                    sku_object['wholesale_price']=str('0.00')
                if sku_object['cost_price'] is None:
                    sku_object['cost_price']=str('0.00')

                order_sku.retail_price = Decimal(sku_object['retail_price'])
                order_sku.wholesale_price = Decimal(sku_object['wholesale_price'])
                order_sku.cost_price = Decimal(sku_object['cost_price'])
                order_sku.save()
            except Exception as e:
                print(order.id , ' : ', order_sku.sku_id)
                # print(sku_object['retail_price'])
                # print(sku_object['wholesale_price'])
                # print(sku_object['cost_price'])
                # print(' Decimal Error ')

        # Remove any extras that are not in the current selection
        OrderSKU.all_objects \
            .filter(order=order)\
            .exclude(sku_id__in=existing) \
            .delete(force=True)

        order.update_missing_selections_status()
        order.save()

    def update_special_features(self, request, order, special_features):
        # Checking that we don't have 2 special features defined for the same department
        errors = []
        category_ids = [special_feature.get('sku_category') for special_feature in special_features]
        duplicates = set([cat_id for cat_id in category_ids if category_ids.count(cat_id) > 1])
        duplicates = [str(department) for department in SKUCategory.objects.filter(id__in=duplicates).exclude(parent=SKUCategory.top())]
        for name in duplicates:
            errors.append(ValidationError('The department {} have several special features defined, please merge them into one.'.format(name)))

        if errors:
            raise ValidationError(errors)

        ids = []  # Track ids, so we can delete stale features
        for special_feature_data in special_features:

            # Filter out all unwanted fields and transforming required fields to the appropriate format
            special_feature_fields = {
                'id': special_feature_data.get('id'),
                'order': order,
                'customer_description': special_feature_data.get('customer_description') or '',
                'retail_price': special_feature_data.get('retail_price'),
                'wholesale_price': special_feature_data.get('wholesale_price'),
                'sku_category_id': special_feature_data.get('sku_category'),
                'factory_description': special_feature_data.get('factory_description') or '',
                'approved': special_feature_data.get('approved'),
                'reject_reason': special_feature_data.get('reject_reason') or '',
            }

            if 'document' not in special_feature_data:
                special_feature_fields.update({'document': None})

            if 'new_document' in special_feature_data:
                special_feature_fields.update({'document': request.FILES.get(str(special_feature_data.get('file_id')))})

            special_feature_id = special_feature_data.get('id')

            if special_feature_id:
                # Using qs.filter().update(...) wouldn't trigger pre/post save signals and wouldn't create an Audit instance
                # https://code.djangoproject.com/ticket/12184
                try:
                    special_feature = SpecialFeature.objects.get(id=special_feature_id)

                    for field, value in list(special_feature_fields.items()):
                        setattr(special_feature, field, value)

                    special_feature.save()
                    ids.append(special_feature_id)
                except SpecialFeature.DoesNotExist:
                    pass
            else:
                feature = SpecialFeature(**special_feature_fields)
                if not feature.is_blank():
                    feature.save()
                    ids.append(feature.id)

        stale = order.specialfeature_set.exclude(id__in=ids)
        stale.delete()

        previous_status = order.get_special_features_status()
        order.update_special_features_status(request.user)
        new_status = order.get_special_features_status()

        if new_status == Order.STATUS_REJECTED and previous_status != new_status:
            reject_reasons = order.specialfeature_set.filter(approved=False).values_list('reject_reason', flat=True)
            send_email_from_template(
                order,
                order.customer_manager,
                EmailTemplate.EMAIL_TEMPLATE_ROLE_SPECIAL_FEATURES_REJECTED,
                request,
                'The special features have been correctly marked as rejected.',
                reject_reason=' ; '.join(reject_reasons),
            )

    def update_show_special(self, order, show_special):
        OrderShowSpecial.objects.filter(order=order).delete()

        if len(show_special.get('applied_rules', [])) == 0:
            return  # No rules were applied for this special, hence no discounts

        order_special = OrderShowSpecial.objects.create(order=order, special_id=show_special['id'])

        for rule_id in show_special['applied_rules']:
            rule = Rule.objects.get(id=rule_id)
            if rule.type == Rule.RULE_PRICE_ADJUSTMENT:
                line_item = OrderShowSpecialLineItem()
                line_item.order_show_special = order_special
                line_item.name = rule.title
                line_item.description = rule.text
                line_item.price_adjustment = rule.price_adjustment
                line_item.save()

    def update_order_conditions(self, order, orderconditions_data):
        try:
            orderconditions = order.orderconditions
        except ObjectDoesNotExist:
            orderconditions = OrderConditions(order=order)

        orderconditions.details = orderconditions_data.get('details', '')
        orderconditions.fulfilled = orderconditions_data.get('fulfilled', False)
        orderconditions.save()

    def update_after_market_note(self, order, aftermarketnote_data):
        try:
            aftermarketnote = order.aftermarketnote
        except ObjectDoesNotExist:
            aftermarketnote = AfterMarketNote(order=order)

        aftermarketnote.note = aftermarketnote_data.get('note', '')
        aftermarketnote.save()

    def is_note_updated(self, data):
        if data.get('orderconditions') or data.get('aftermarketnote') or data.get('trade_in_comment'):
           return True

        return False

    def update_note_details(self, data, order):

        if data.get('orderconditions') is not None:
            self.update_order_conditions(order, data['orderconditions'])

        if data.get('aftermarketnote') is not None:
            self.update_after_market_note(order, data['aftermarketnote'])

        if data.get('trade_in_comment'):
            order.trade_in_comment = data.get('trade_in_comment') or ''

        order.save()

class UpdateSalesforce(JSONExceptionAPIView):
    permission_required = "orders.view_or_create_or_modify_order"

    default_error_message = 'An error occurred while updating Salesforce.'

    def post(self, request):

        order_id = request.data.get('order_id')

        if not request.user.has_perm('orders.modify_order'):
            return HttpResponseForbidden()

        order = Order.objects.get(id=order_id)
        order.sync_salesforce(request.build_absolute_uri('/'))
        return JsonResponse({})


class SaveOrderNote(JSONExceptionAPIView,APIView):
    permission_classes = [IsAuthenticated]
    # permission_required = "orders.view_or_create_or_modify_order"

    default_error_message = 'An error occurred while saving the Notes.'

    def post(self, request):
        # print('POST Requested ')
        # print(request.data.POST.get['dealership'])
        # print('JSON :', request.body)
        # print('AJAX : ',request.data)
        # print('Entered Note Section Test')

        data = json.loads(request.body.decode("utf-8"))

        # print('Recvd JSON data', data)

       

        try:
            order= Order.objects.get(id=data.get('order_id'))
        except ObjectDoesNotExist:
            return JsonResponse({"Error:" : "Invalid Order Id !! "  })

        # print( 'Id ' , request.user.id ) 
        # print( ' Name ', request.user.name)
        User = get_user_model()
        try:
            user= User.objects.get(id=data.get('user_id'))
        except ObjectDoesNotExist:
            return JsonResponse({"Error:" : "Invalid Order Id !! "  })
        
        print('From authtools ',user.id)
        

        notes = data.get('notes')

        if notes is None :
            return JsonResponse({"Error:" : " Notes are Empty  !! "  })            

        # print(' Order Id ' , order.id)

        # print(' User Id ' , request.user.id)

        # print(' Notes ' , notes)

        # print(' Note Status ' , data.get('note_status') )


        today = datetime.now()  
        # str_now = datetime.now().isoformat()
        ordernote=OrderNote()
        ordernote.order_id=order.id
        ordernote.note = notes 
        ordernote.note_date = str(today)  
        ordernote.note_status = 'appRetail'
        ordernote.user_id = request.user.id

        ordernote.save()


        return JsonResponse({"Success" : "Note Successfully Updated  " })
