from datetime import datetime
from collections import defaultdict

from allianceutils.views.views import JSONExceptionAPIView
from django.db.models import Q
from django.db.models import Avg
from django.http import JsonResponse
from django.http.response import HttpResponseBadRequest
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from rest_framework.response import Response

from caravans.models import Model
from caravans.models import Rule
from caravans.models import Series
from caravans.models import SeriesSKU
from caravans.models import SKUPrice
from caravans.models import SKUCategory
from caravans.serializers import ModelSerializer
from caravans.serializers import RuleSerializer
from caravans.serializers import SeriesSerializer
from caravans.serializers import SKUSerializer
from customers.models import AcquisitionSource
from customers.models import Customer
from customers.models import SourceOfAwareness
from customers.serializers import CustomerSerializer
from dealerships.models import Dealership
from dealerships.models import DealershipUserDealership
from newage.models import State
from orders.models import Order
from orders.models import Show
from orders.models import ShowSpecial
from schedule.models import DealerMonthPlanning
from production.models import Build
from orders.serializers import ShowSpecialSerializer
from orders.views.api.utils import dropdown_item
from orders.views.api.utils import get_all_delivery_months
from orders.views.api.utils import get_available_delivery_months
from orders.views.api.order_workflow import get_dealer_ordercount_month


def serialize_rule(rule, series_id):
    rule_data = RuleSerializer(rule).data
    for sku in rule_data['items']:
        # Need to find a matching SeriesSKU for this SKU
        s_sku = SeriesSKU.objects.filter(
            series_id=series_id,
            sku_id=sku['id'],
        ).first()
        if s_sku is not None:
            sku['series_sku_id'] = s_sku.pk
            sku['availability_type'] = s_sku.availability_type
            sku['availability_type_name'] = s_sku.get_availability_type_display()
    return rule_data


class SearchOrders(JSONExceptionAPIView):
    permission_required = "orders.view_order"

    default_error_message = 'An error occurred while searching for orders.'

    @staticmethod
    def post(request):
        text = request.data.get('filter')
        order_dealership = Dealership.objects.get(id=request.data.get('dealership'))
        dealership_ids = [dealership.id for dealership in Dealership.objects.filter(dealershipuser=request.user)]
        orders = (Order.objects
             .filter(dealership_id__in=dealership_ids,
                     orderseries__isnull=False,
                     orderseries__series__dealerships=order_dealership)
             .filter(Q(customer__first_name__icontains=text) |
                     Q(customer__last_name__icontains=text) |
                     Q(chassis__icontains=text))[:30])
        result = [{
            'id': order.id,
            'title': str(order)
        } for order in orders]
        return JsonResponse({'list': result})


class ShowroomData(JSONExceptionAPIView):
    permission_required = "orders.create_order"

    default_error_message = 'An error occurred while getting initial data.'

    def post(self, request):
        models = []
        for model in Model.objects.all():
            series = Series.objects.filter(model=model)
            if len(series) == 0:
                continue
            try:
                logo_url = model.logo.url
            except ValueError:
                logo_url = None
            models.append({
                'id': model.id,
                'name': model.name,
                'logo': logo_url,
                'series': SeriesSerializer(series, many=True).data,
            })

        now = timezone.now()

        dealerships = Dealership.objects.all()
        if request.user.has_perm('orders.create_order_all'):
            pass
        else:
            dealerships = dealerships.filter(dealershipuser=request.user)

        return JsonResponse(
            {
                'models': models,
                'states': [{'code': s.code, 'title': s.name} for s in State.objects.all()],
                'acquisition_source': [dropdown_item(i) for i in AcquisitionSource.objects.all()],
                'source_of_awareness': [dropdown_item(i) for i in SourceOfAwareness.objects.all()],
                'shows': [dropdown_item(i) for i in Show.objects.filter(start_date__lte=now, end_date__gte=now)],
                'available_delivery_months': get_available_delivery_months(include_previous_months = False, production_unit=1),
                'dealerships': [dropdown_item(i) for i in dealerships],
            }
        )

class Showroom2Data(JSONExceptionAPIView):
    permission_required = "orders.create_order"

    default_error_message = 'An error occurred while getting initial data.'

    def post(self, request):
        models = []
        for model in Model.objects.all():
            series = Series.objects.filter(model=model)
            if len(series) == 0:
                continue
            try:
                logo_url = model.logo.url
            except ValueError:
                logo_url = None
            models.append({
                'id': model.id,
                'name': model.name,
                'logo': logo_url,
                'series': SeriesSerializer(series, many=True).data,
            })

        now = timezone.now()

        dealerships = Dealership.objects.all()
        if request.user.has_perm('orders.create_order_all'):
            pass
        else:
            dealerships = dealerships.filter(dealershipuser=request.user)

        return JsonResponse(
            {
                'models': models,
                'states': [{'code': s.code, 'title': s.name} for s in State.objects.all()],
                'acquisition_source': [dropdown_item(i) for i in AcquisitionSource.objects.all()],
                'source_of_awareness': [dropdown_item(i) for i in SourceOfAwareness.objects.all()],
                'shows': [dropdown_item(i) for i in Show.objects.filter(start_date__lte=now, end_date__gte=now)],
                'available_delivery_months': get_available_delivery_months(include_previous_months = False, production_unit=2),
                'dealerships': [dropdown_item(i) for i in dealerships],
            }
        )

class InitialData(JSONExceptionAPIView):
    permission_required = "orders.view_or_create_or_modify_order"

    default_error_message = 'An error occurred while getting initial data.'

    

    def post(self, request):
        def category_item(category):
            item = dropdown_item(category)
            item['departments'] = [dropdown_item(d) for d in category.skucategory_set.all()]
            return item

        permissions = {
            'view_order_cost_price': request.user.has_perm('orders.view_order_cost_price'),
            'modify_order_cost_price': request.user.has_perm('orders.modify_order_cost_price'),     # TODO: Verify if this exists
            'list_customer': request.user.has_perm('customers.list_customer'),
            'modify_order_trade_price': request.user.has_perm('orders.modify_order_trade_price'),
            'modify_order_retail_price': request.user.has_perm('orders.modify_order_retail_price'),
            'print_for_autocad': request.user.has_perm('orders.print_for_autocad'),
            'view_production_data': request.user.has_perm('orders.view_production_data'),
            'reassign_stock_orders': request.user.has_perm('orders.reassign_stock_orders'),
            'create_order': request.user.has_perm('orders.create_order'),
            'modify_special_features_wholesale': request.user.has_perm('orders.modify_special_features_wholesale'),
            'modify_special_features': request.user.has_perm('orders.modify_special_features'),
            'manual_override': request.user.has_perm('orders.manual_override'),
            'approve_special_features': request.user.has_perm('orders.approve_special_features'),
            'set_custom_series': request.user.has_perm('orders.set_custom_series'),
            'can_create_edit_customer_details': request.user.has_perm('orders.can_create_edit_customer_details'),
            'can_override_dealer_capacity':request.user.has_perm('orders.can_override_dealer_capacity'),
        }

        order_id = request.data.get('order_id')
        order = Order.objects.filter(id=order_id).first()

        if order is None:
            # If user doesn't have permission to view order, he is still able to view the current order if he can create it
            permissions['view_order'] = permissions['create_order']
        else:

            try:
                # Dealer principal should be able to change the retail price
                DealershipUserDealership.objects.get(dealership_user_id=request.user.id, dealership=order.dealership, is_principal=True)
                permissions['modify_order_retail_price'] = True
            except DealershipUserDealership.DoesNotExist:
                pass

            permissions['view_order'] = request.user.has_perm('orders.view_order', order)
            permissions['modify_order_requested'] = request.user.has_perm('orders.modify_order_requested', order)
            permissions['view_order_trade_price'] = request.user.has_perm('orders.view_order_trade_price', order)
            permissions['print_invoice'] = request.user.has_perm('orders.print_invoice', order)



        dealerships = Dealership.objects.all()
        if request.user.has_perm('orders.create_order_all'):
            pass
        else:
            dealerships = dealerships.filter(dealershipuser=request.user)

        now = timezone.now()

        user_data=0
        # print('Count Dealer : ', dealerships.filter(dealershipuser=request.user).count())
        if(dealerships.filter(dealershipuser=request.user).count()>0):
            user_data=1
        else:
            user_data=0


        # Special Request For the Following Users 
        # John Wijnen # Adrian Di Vincenzo # Paoli Josh # Nick Kemp # Nishan Somaratna 
        if ((request.user.id == 32) or (request.user.id == 31 ) or (request.user.id == 171 ) or (request.user.id == 298) or (request.user.id == 272)):
            user_data=0         

        available_delivery_months = get_available_delivery_months(include_previous_months = request.user.has_perm('orders.manual_override'), production_unit=1)
        
        if order and order.delivery_date and order.delivery_date not in available_delivery_months:
            available_delivery_months.append(order.delivery_date)
            available_delivery_months = sorted(available_delivery_months)

        show_list = [dropdown_item(i) for i in Show.objects.filter(start_date__lte=now, end_date__gte=now)]
        if order and order.show and dropdown_item(order.show) not in show_list:
            show_list.append(dropdown_item(order.show))

        user_details = list(dealerships.filter(dealershipuser=request.user).values('dealershipuser','dealershipuserdealership')) if dealerships.filter(dealershipuser=request.user).exists() else None,
        # print(user_details)

        permissions['user_details']=user_data
        # print(permissions)
        all_delivery_months_list=[]
        available_delivery_months_list=[]

        if request.user.has_perm('orders.can_override_dealer_capacity') is False:
        
            # print('initial data permission false')
            if 'dealership_id' in request.data:
                dealer_id=request.data.get('dealership_id')
                if dealer_id is not None:  
                    all_delivery_months=get_all_delivery_months(include_previous_months=request.user.has_perm('orders.manual_override'), production_unit=1)
                    all_delivery_months_list=date_assignment(dealer_id,all_delivery_months)
                    available_delivery_months_list=date_assignment(dealer_id,available_delivery_months)
        else:
            all_delivery_months_list=get_all_delivery_months(include_previous_months=request.user.has_perm('orders.manual_override'), production_unit=1)
            available_delivery_months_list=available_delivery_months
            
        initial_data = {
            'dealerships': [dropdown_item(i) for i in dealerships],
            'categories': [category_item(i) for i in SKUCategory.top().skucategory_set.all()],
            'models': [dropdown_item(i) for i in Model.objects.all() if i.series_set.filter(dealerships=request.data.get('dealership_id')).count()],
            'states': [{'code': s.code, 'title': s.name} for s in State.objects.all()],
            'acquisition_source': [dropdown_item(i) for i in AcquisitionSource.objects.all()],
            'source_of_awareness': [dropdown_item(i) for i in SourceOfAwareness.objects.all()],
            'shows': show_list,
            'available_delivery_months': available_delivery_months_list,
            'all_delivery_months':  all_delivery_months_list,
            'permissions': permissions,
        }


        if request.data.get('customer_id'):
            try:
                customer = Customer.objects.get(id=request.data.get('customer_id'))
                initial_data['customer_info'] = CustomerSerializer(customer).data
            except Customer.DoesNotExist:
                pass

        return JsonResponse(initial_data)


class ItemRules(JSONExceptionAPIView):
    permission_required = "orders.modify_order"

    default_error_message = 'An error occurred while getting rules associated with selected item.'

    def post(self, request):
        data = request.data
        rules = Rule.objects.filter(
            series=data.get('series_id'),
            sku_id=data.get('sku_id'))

        rules_list = []
        for r in rules:
            rules_list.append(serialize_rule(r, data.get('series_id')))

        result = {
            'rules': rules_list
        }

        return JsonResponse(result)


class ModelSeries(JSONExceptionAPIView):
    permission_required = "orders.view_or_create_or_modify_order"

    default_error_message = 'An error occurred while getting model information.'

    def post(self, request):
        data = request.data
        model = Model.objects.get(id=data.get('model_id'))
        model_detail = ModelSerializer(model).data
        
        order_id = request.data.get('order_id')
        order = Order.objects.filter(id=order_id).first()

        available_delivery_months = get_available_delivery_months(include_previous_months = request.user.has_perm('orders.manual_override'), production_unit=1)
        

        if order and order.delivery_date and order.delivery_date not in available_delivery_months:
            available_delivery_months.append(order.delivery_date)
            available_delivery_months = sorted(available_delivery_months)
            

        permissions = {'manual_override' : request.user.has_perm('orders.manual_override'),
        'can_create_edit_customer_details': request.user.has_perm('orders.can_create_edit_customer_details'),}
        
        all_delivery_months_list=[]
        available_delivery_months_list=[]

        if request.user.has_perm('orders.can_override_dealer_capacity') is False:
        
            if 'dealership_id' in request.data:
                dealer_id=request.data.get('dealership_id')
                if dealer_id is not None:  
                    all_delivery_months=get_all_delivery_months(include_previous_months=request.user.has_perm('orders.manual_override'), production_unit=1)
                    all_delivery_months_list=date_assignment(dealer_id,all_delivery_months)
                    available_delivery_months_list=date_assignment(dealer_id,available_delivery_months)
        else:
            all_delivery_months_list=get_all_delivery_months(include_previous_months=request.user.has_perm('orders.manual_override'), production_unit=1)
            available_delivery_months_list=available_delivery_months

        result = {
            'series': [{
                'id': series.id,
                'title': '%s (%s)' % (series.name, series.code),
            } for series in Series.objects.filter(model=model, dealerships=data.get('dealership_id'))],
            'model_detail': model_detail,
            'available_delivery_months': available_delivery_months_list,
            # 'all_delivery_months': get_all_delivery_months(include_previous_months=request.user.has_perm('orders.manual_override'), production_unit=1),
            'all_delivery_months': all_delivery_months_list, #get_all_delivery_months(include_previous_months=False, production_unit=1),
            'permissions':permissions,
           
        }

        return JsonResponse(result)
        
    
# class DeliveryMonth(JSONExceptionAPIView):
#     permission_required = "orders.view_or_create_or_modify_order"

#     default_error_message = 'An error occurred while getting series information.'

#     def post(self, request):
#         data = request.data
#         series = Series.objects.get(pk=data.get('series_id'))

#         production_unit = series.production_unit

#         data = {
#         'available_delivery_months' : get_available_delivery_months(include_previous_months = request.user.has_perm('orders.manual_override'), production_unit=production_unit),
#         'all_delivery_months': get_all_delivery_months(include_previous_months=request.user.has_perm('orders.manual_override'), production_unit=production_unit),
#         }

#         return JsonResponse(data)

class SeriesDetail(JSONExceptionAPIView):
    permission_required = "orders.view_or_create_or_modify_order"

    default_error_message = 'An error occurred while getting series information.'

    def post(self, request):
        data = request.data
        series = Series.objects.get(pk=data.get('series_id'))
        # model_id=Series.objects.get(pk=data.get('model_id'))
        
        # print('Data : ',data)

        # print(' Reqd Date : ', data.get('required_date'))
        
        # if data.get('required_date') is None:
        #     return JsonResponse(data)
        # print(' Series Detail First  Response !!!! ')
        # dealer_id= data.get('dealership_id')
        # dealer_id=request.data.get('dealership_id')

      

        series_id= series.id

        order = Order.objects.select_related('orderseries').get(id=data["order_id"])

        # print('Series Dealer Detail : ', order.dealership_id )

        dealer_id = order.dealership_id 

        detail = SeriesSerializer(series, order=order).data
        
        if data.get('required_date'):
            requested_delivery_month = datetime.strptime(data.get('required_date').split("T")[0], settings.FORMAT_DATE_ISO).date()
        else:
            requested_delivery_month = order.delivery_date
            # raise ValidationError('You need to select Desired Delivery Month .')
        # requested_delivery_month = datetime.strptime(data.get('delivery_date').split("T")[0], settings.FORMAT_DATE_ISO).date()
        # print(requested_delivery_month)
        Order.objects.filter(id=order.id).update(delivery_date=requested_delivery_month)

        available_delivery_months = get_available_delivery_months(include_previous_months = request.user.has_perm('orders.manual_override'), production_unit=1)

        if order and order.delivery_date and order.delivery_date not in available_delivery_months:
            available_delivery_months.append(order.delivery_date)
            available_delivery_months = sorted(available_delivery_months)
            
        all_delivery_months = get_all_delivery_months(include_previous_months=request.user.has_perm('orders.manual_override'), production_unit=1)
        
        all_delivery_months_list=[]
        available_delivery_months_list=[]

        if request.user.has_perm('orders.can_override_dealer_capacity') is False:
        
            # print('Series Detail permission false')
            all_delivery_months_list=date_assignment(dealer_id,all_delivery_months)
        
            available_delivery_months_list=date_assignment(dealer_id,available_delivery_months)
        else:
            all_delivery_months_list =all_delivery_months
            available_delivery_months_list =available_delivery_months

        show_specials = ShowSpecial.objects.filter(
            available_from__lte=order.created_on,
            available_to__gte=order.created_on,
            rules__series=series
        )

        # print('Available :', available_delivery_months)
        # print('#$@#$#@$#@$#@$@#####################')
        # print('All Dates :', all_delivery_months)
        if not self.request.user.has_perm('orders.apply_specials_all'):
            show_specials = show_specials.filter(dealerships=order.dealership)

        if hasattr(order, 'orderseries'):
            detail['cost_price'] = order.orderseries.cost_price
            detail['wholesale_price'] = order.orderseries.wholesale_price
            detail['retail_price'] = order.orderseries.retail_price

        detail['show_specials'] = []


        for show_special in show_specials:
            show_special_details = ShowSpecialSerializer(show_special).data
            show_special_details['rules'] = [serialize_rule(r, data.get('series_id')) for r in show_special.rules.all()]
            detail['show_specials'].append(show_special_details)

        detail['available_delivery_months'] = available_delivery_months_list
        detail['all_delivery_months'] = all_delivery_months_list

        permissions = {'manual_override' : request.user.has_perm('orders.manual_override'),
        'can_create_edit_customer_details': request.user.has_perm('orders.can_create_edit_customer_details'),}
        detail['permissions'] = permissions  
        # Add the average weight logic here 
        # For all stock vans after 01-04-2020
        # Two Conditions 
        #check if this is a customer van continue with the following calculation model -- dont take averages
        # This order does not already have weights set --- then implement till the previoud order excluding this order
        order_list = Order \
            .objects \
            .filter(
            order_submitted__gte='2020-04-01 0:0:0',
            order_cancelled__isnull=True,
            is_order_converted=0,
            customer_id__isnull=True,
            orderseries__series_id=series_id,
            # dispatch_date_actual__gte = month_start,
            # dispatch_date_actual__lte = today,
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
            'build__drafter',) \
            .prefetch_related('orderdocument_set',) \
            .exclude(build__weight_tare=0) \
            .exclude(build__weight_tow_ball=0) \
            .values_list('id','chassis','orderseries__series_id','dealership','build__weight_tare','build__weight_tow_ball')


        avg_ball1 =  order_list.aggregate(avg_tare=Avg('build__weight_tare'),avg_ball=Avg('build__weight_tow_ball')) 
        # print('Series Id',series_id)
        # print(order_list)
        # print(' Record Count ' ,len(order_list))
        # print(avg_ball1)
        if avg_ball1['avg_tare'] is not None:
            # print('Entering None')
            # print('Tare Avg : ',round(avg_ball1['avg_tare']) ,'Tare Ball '': ', round(avg_ball1['avg_ball']) )
            avg_tare = round(avg_ball1['avg_tare'])
            avg_ball = round(avg_ball1['avg_ball'])
        else:
            avg_tare=0
            avg_ball=0


        if(len(order_list)>0):
            detail['avg_tare_weight'] = avg_tare
            detail['avg_ball_weight'] = avg_ball 
        else:
            detail['avg_tare_weight'] = 0
            detail['avg_ball_weight'] = 0 

        # print('detail data',detail['avg_tare_weight']    ,' : ',detail['avg_ball_weight'])
        # detail['avg_tare_weight'] = series.avg_tare_weight if series.avg_tare_weight else 0    
        # detail['avg_ball_weight'] = series.avg_ball_weight if series.avg_ball_weight else 0
        # detail['avg_tare_weight'] = series.avg_tare_weight if series.avg_tare_weight else 0
        detail['length_aframe'] = series.length_incl_aframe_mm if series.length_incl_aframe_mm else 0
        detail['length_bumper'] = series.length_incl_bumper_mm if series.length_incl_bumper_mm else 0
        detail['width_awning'] = series.width_incl_awning_mm if series.width_incl_awning_mm else 0
        detail['height_ac'] = series.height_max_incl_ac_mm if series.height_max_incl_ac_mm else 0

        print(' Exit Series Detail And Send Response !!!! ')

        return JsonResponse(detail)

class SeriesItems(JSONExceptionAPIView):
    permission_required = "orders.view_or_create_or_modify_order"

    default_error_message = 'An error occurred while getting the series list of items.'

    def get(self, request):
        data = request.data or request.GET
        
        print(' Enter Series Items  !!!! ')
        
        if data.get('order_id'):
            order = Order.objects.get(id=data.get('order_id'))

        if data.get('required_date') :
            requested_delivery_month = datetime.strptime(data.get('required_date').split("T")[0], settings.FORMAT_DATE_ISO).date()
        else:
            requested_delivery_month= order.delivery_date
            # raise ValidationError('You need to select Desired Delivery Month .')
        

        if not order.delivery_date:
            # return HttpResponseBadRequest(' Select the Delivery Date ! ')
            return JsonResponse({'a':'a'})
        else:
            print(order.delivery_date)


        result = self.generate_categories(data.get('series_id'), data.get('order_id'), order.delivery_date)
        
        print(' Exit Series Items  !!!!! ')

        # permissions = {'manual_override' : request.user.has_perm('orders.manual_override'),
        # 'can_create_edit_customer_details': request.user.has_perm('orders.can_create_edit_customer_details'),}
        # detail['permissions'] = permissions
        
        return Response(result)

    @staticmethod
    def generate_categories(series_id, order_id,requested_delivery_month):

        order_categories = []
        order_availability = {}
        is_order_finalized = False
        # If order is finalised, compute the list of category and availability for easier filtering later
        try:
            order = Order.objects.get(id=order_id)
            if order.get_finalization_status() == Order.STATUS_APPROVED:
                is_order_finalized = True
                order_categories = set()
                order_availability = {}
                for osku in order.ordersku_set.all().select_related('sku__sku_category'):
                    order_categories.add(osku.sku.sku_category)
                    order_availability[osku.sku_id] = osku.base_availability_type

        except Order.DoesNotExist:
            pass

        sku_categories = SKUCategory.top().skucategory_set.all()\
            .prefetch_related('skucategory_set')

        series_skus = SeriesSKU.objects\
            .filter(series_id=series_id, is_visible_on_spec_sheet=True)\
            .select_related('sku__sku_category')\
            .order_by('sku__sku_category__name', 'sku__name')

        # Organize data to have a dict skus[category_id][availability] = list of skus
        skus = defaultdict(lambda: defaultdict(list))

        for series_sku in series_skus:
            availability = series_sku.availability_type

            if is_order_finalized:
                # Take ordersku availability if defined, otherwise keep the seriessku availability
                availability = order_availability.get(series_sku.sku_id, availability)

                if series_sku.sku.sku_category not in order_categories and availability != SeriesSKU.AVAILABILITY_OPTION:  # We always want the full list of available optional extras for selection
                    continue

            sku = SKUSerializer(series_sku.sku, availability_type=series_sku.availability_type).data
            skus[series_sku.sku.sku_category_id][availability].append(sku)

        category_list = [
            {
                'id': category.id,
                'name': category.name,
                'departments': [
                    {
                        'id': department.id,
                        'name': department.name,
                        'read_only': department.read_only,
                        # Selections also include the standard items
                        'selections': skus.get(department.id, {}).get(SeriesSKU.AVAILABILITY_STANDARD, []) + skus.get(department.id, {}).get(SeriesSKU.AVAILABILITY_SELECTION, []),
                        'upgrades': skus.get(department.id, {}).get(SeriesSKU.AVAILABILITY_UPGRADE, []),
                        'options': skus.get(department.id, {}).get(SeriesSKU.AVAILABILITY_OPTION, []),
                    }
                    for department in category.skucategory_set.filter(id__in=list(skus.keys())) # Only departments available for the series
                ]
            }
            for category in sku_categories
        ]


        # print(category_list)
        # print('Before Eff Calc!')
        # Call function to get the sku price based on the effective date 
        selected_effective_date = select_sku_effective_date(requested_delivery_month)

        # print ('sel Date : ', selected_effective_date)
        
        # sku_price= SKUPrice(sku_id,selected_effective_date)
        
        def get_new_sku(sku_id,selected_effective_date,exist_price,check_val):
            
            # print('Inside Function : sku_id ', sku_id , ' : Exist : ' , exist_price , 'check val ',check_val)
            
            try:
                if (SKUPrice.objects.filter(sku_id=sku_id,effective_date=selected_effective_date).exists()):
                    sku_price = SKUPrice.objects.filter(sku_id=sku_id,effective_date=selected_effective_date).values_list(str(check_val),flat=True)[0] 
                    # print('DB Fetch : sku_id ', sku_id, ' : New Price ', sku_price)
                    if sku_price :
                        return str(sku_price)
                    else:
                        return str('0.00')
                else:
                    return str(exist_price)
            except SKUPrice.DoesNotExist:
                return str(exist_price)


        for c_test in category_list:

            # print('CHASSIS')
            # print('Name :',c_test['name'])
            if c_test['name'] == 'CHASSIS':
                # print('CHASSIS')
                for d_test in c_test['departments']:
                    for sel_test in d_test['selections']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price')
                    
                    for sel_test in d_test['upgrades']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price')

                    
                    for sel_test in d_test['options']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price')

            if c_test['name'] == 'FURNITURE':
                # print('FURNITURE')
                for d_test in c_test['departments']:
                    for sel_test in d_test['selections']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price')
                    
                    for sel_test in d_test['upgrades']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price')

                    
                    for sel_test in d_test['options']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price')

            if c_test['name'] == 'PLUMBING':
                # print('PLUMBING')
                for d_test in c_test['departments']:
                    for sel_test in d_test['selections']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price')
                    
                    for sel_test in d_test['upgrades']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price')

                    
                    for sel_test in d_test['options']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price')

             
            
            if c_test['name'] == 'ELECTRICAL':
                # print('ELECTRICAL')
                for d_test in c_test['departments']:
                    for sel_test in d_test['selections']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price') 
                    
                    for sel_test in d_test['upgrades']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price') 

                    for sel_test in d_test['options']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price')

            
            if c_test['name'] == 'ALUMINIUM':
                # print('ALUMINIUM')
                for d_test in c_test['departments']:
                    for sel_test in d_test['selections']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price') 
                
                    for sel_test in d_test['upgrades']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price') 

                    for sel_test in d_test['options']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price') 

           

            
            if c_test['name'] == 'FINISHING':
                # print('FINISHING')
                for d_test in c_test['departments']:
                    for sel_test in d_test['selections']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price') 
                
                    for sel_test in d_test['upgrades']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price') 

                    for sel_test in d_test['options']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price') 

            
            if c_test['name'] == 'UPHOLSTERY':
                # print('UPHOLSTERY')
                for d_test in c_test['departments']:
                    for sel_test in d_test['selections']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price') 
                
                    for sel_test in d_test['upgrades']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price') 

                    for sel_test in d_test['options']:
                        sel_test['wholesale_price'] = get_new_sku(sel_test['id'],selected_effective_date,sel_test['wholesale_price'],'wholesale_price') 
                        sel_test['retail_price']=get_new_sku(sel_test['id'],selected_effective_date,sel_test['retail_price'],'retail_price') 
                        sel_test['cost_price']= get_new_sku(sel_test['id'],selected_effective_date,sel_test['cost_price'],'cost_price') 

         
        print('Desired Date : ', requested_delivery_month)
        
        # print(' Desired Date : ', order.delivery_date)
        # print(category_list)
        
        return {'categories': category_list}

# Function Which Calculates the  Effective Dates. 
def select_sku_effective_date(requested_delivery_month):
    all_dates = set(list(SKUPrice.objects.all().order_by('effective_date').values_list('effective_date',flat=True)))
    # new_list=set(all_dates)
    # print('Inside Effective Date Calculation !! ')

    my_list=[]
    diff_list=[]
    diff=0
    index=0
    dict_list=[]
    for x in all_dates:
        
        my_dict={}
        my_list.append(x)
        diff =(requested_delivery_month-x).days
        my_dict={'effective_date':x,'diff':diff}
        dict_list.append(my_dict)
        if(diff>=0):
            diff_list.append(diff)
            # pos=index
        index=index + 1
    
    pos=min(diff_list)
    res = [j['effective_date'] for i, j in enumerate(dict_list) if int(j['diff']) == int(pos)] 
    # print('Eff Date:',res)

    for j in dict_list:
        if int(j['diff']) == int(pos):
            get_val=j['effective_date'] 

    print('Required Effective Date : ',get_val)

    return get_val

def check_dealer_quota_month(dealership_id,reqd_production_month):
        try:
            dealer_capacity_allotted = DealerMonthPlanning.objects.get(production_month=reqd_production_month,dealership_id=dealership_id)
        except DealerMonthPlanning.DoesNotExist as e:
            print(e)
            return HttpResponseBadRequest('Please assign Dealership Capacity for all scheduled months') 

        
        
        dealer_order_count = get_dealer_ordercount_month(dealership_id,reqd_production_month)


        if (dealer_order_count >= dealer_capacity_allotted.capacity_allotted):
            return False 
        else:
            return True

def date_assignment(dealer_id=None,delivery_months=None):
    month_list=[]
    for month in delivery_months:
        

        if check_dealer_quota_month(dealer_id,month):
            month_list.append(month)
    return month_list