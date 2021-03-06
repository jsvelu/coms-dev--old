from datetime import timedelta
import inspect
import sys

from django.db.models import Q
from django.db.models.expressions import Value
from django.db.models.fields import CharField
from django.utils import timezone

from audit.models import Audit
from orders.models import Order
from orders.models import OrderDocument


class BaseTodoAction(object):
    """
    This class defines the base class for filtering the orders that should show up in a given user todo list
    """

    manage_url = '/status' # The url the manage link should point to for this item

    @staticmethod
    def get_order_list(user):
        """
        This method returns an iterable of Orders to be displayed in the todo list for the given user.
        The items of the query should be annotated with the action name, using `annotate(action_name='Action Required')
        Args:
            user: The user for whom we need to set the order list

        Returns: An iterable of orders (can be empty)

        """
        return Order.objects.none()


class SalesRepAmendOrderTodo(BaseTodoAction):
    """
    Orders to be amended for approval
    For Sales Rep
    """

    @staticmethod
    def get_order_list(user):
        orders = Order.objects.filter(
            order_cancelled__isnull=True,
            customer_manager_id=user,
            order_requested__isnull=False,
            order_rejected__isnull=False,
            order_submitted__isnull=True
        )\
            .annotate(action_name=Value('Amend Order', CharField()))\
            .extra(select={'days_waiting': 'DATEDIFF(NOW(), order_rejected)'})\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return [o for o in orders if not o.is_expired()]

class DealerPrincipalApprovalTodo(BaseTodoAction):
    """
    Orders to be approved
    For Dealer Principal
    """

    @staticmethod
    def get_order_list(user):
        try:
            user.dealershipuser
        except user.DoesNotExist:
            return Order.objects.none()

        orders = Order.objects.filter(
            order_cancelled__isnull=True,
            dealership_id__in=user.dealershipuser.get_dealership_principal_ids(),
            order_requested__isnull=False,
            order_rejected__isnull=True,
            order_submitted__isnull=True,
            has_missing_selections=False
        )\
            .annotate(action_name=Value('Waiting Approval', CharField()))\
            .extra(select={'days_waiting': 'DATEDIFF(NOW(), order_requested)'})\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return [o for o in orders if not o.is_expired()]

class StandManagerApprovalTodo(BaseTodoAction):
    """
    Orders to be approved
    For Stand Manager
    """

    @staticmethod
    def get_order_list(user):
        orders = Order.objects.filter(
            Q(show__stand_manager=user) | Q(show__stand_manager_2=user) | Q(show__stand_manager_3=user),
            order_cancelled__isnull=True,
            order_requested__isnull=False,
            order_rejected__isnull=True,
            order_submitted__isnull=True
        )\
            .annotate(action_name=Value('Waiting Approval', CharField()))\
            .extra(select={'days_waiting': 'DATEDIFF(NOW(), order_requested)'})\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return [o for o in orders if not o.is_expired()]


class MissingSelectionsTodo(BaseTodoAction):
    """
    Orders with missing selections
    For Customer Manager
    """

    # Point to feature selection page
    manage_url = '/caravan/features'

    @staticmethod
    def get_order_list(user):
        try:
            user.dealershipuser
        except user.DoesNotExist:
            return Order.objects.none()

        orders = Order.objects.filter(
            order_cancelled__isnull=True,
            customer_manager=user,
            has_missing_selections=True,
        )\
            .annotate(action_name=Value('Complete selections', CharField()))\
            .extra(select={'days_waiting': 'DATEDIFF(NOW(), created_on)'})\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return [o for o in orders if not o.is_quote()]


class UnReviewedSpecialFeaturesTodo(BaseTodoAction):
    """
    Orders with special features to be reviewed
    For any user with `approve_special_features` permission
    """

    # Point to special feature page
    manage_url = '/special_features'

    @staticmethod
    def get_order_list(user):
        if not user.has_perm('orders.approve_special_features'):
            return Order.objects.none()

        orders = Order.objects.filter(
            order_cancelled__isnull=True,
            order_requested__isnull=False,
        )\
            .annotate(action_name=Value('Approve Special Feature', CharField()))\
            .extra(select={'days_waiting': 'DATEDIFF(NOW(), special_features_changed_at)'})\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')
        return [o for o in orders if o.get_special_features_status() == Order.STATUS_PENDING and not o.is_expired()]


class RejectedSpecialFeaturesTodo(BaseTodoAction):
    """
    Orders with special features rejected
    For Dealer Principal and Customer Manager
    """

    # Point to special feature page
    manage_url = '/special_features'

    @staticmethod
    def get_order_list(user):
        try:
            user.dealershipuser
        except user.DoesNotExist:
            return Order.objects.none()

        orders = Order.objects.filter(
            Q(dealership_id__in=user.dealershipuser.get_dealership_principal_ids()) | Q(customer_manager=user),
            order_cancelled__isnull=True,
        )\
            .annotate(action_name=Value('Special Feature Rejected', CharField()))\
            .extra(select={'days_waiting': 'DATEDIFF(NOW(), special_features_rejected_at)'})\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return [o for o in orders if o.get_special_features_status() == Order.STATUS_REJECTED and not o.is_expired()]


class MissingDrafterTodo(BaseTodoAction):
    """
    Orders with chassis number and missing drafter
    For any user with `modify_order_drafter` permission
    """

    @staticmethod
    def get_order_list(user):
        if not user.has_perm('orders.modify_order_drafter'):
            return Order.objects.none()

        orders = Order.objects\
            .exclude(
                chassis=''
            )\
            .filter(
                order_cancelled__isnull=True,
                build__drafter__isnull=True,
            )\
            .annotate(action_name=Value('Assign Drafter', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return [o for o in orders if o.get_finalization_status() == Order.STATUS_APPROVED]


class MissingCustomerPlansTodo(BaseTodoAction):
    """
    Orders with missing customer plan
    For assigned drafter
    """

    @staticmethod
    def get_order_list(user):
        orders = Order.objects\
            .filter(
                order_cancelled__isnull=True,
                build__drafter=user,
            ).annotate(action_name=Value('Draft plans', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        # Using a function here so that the result can be accessed with `order.days_waiting` just as if this value had been added using a `.extra(...)` on the queryset
        def add_days_waiting(order):
            if hasattr(order, 'build') and Audit.get_last_change(order.build, 'drafter') is not None:
                assigned_at = Audit.get_last_change(order.build, 'drafter')['saved_on']
                order.days_waiting = (timezone.now() - assigned_at).days
            return order

        return [add_days_waiting(o) for o in orders if o.get_customer_plan_status() == Order.STATUS_NONE and o.get_finalization_status() == Order.STATUS_APPROVED]


class PrepareFactoryChassisPlansTodo(BaseTodoAction):
    """
    Orders with missing factory and chassis plans
    For assigned drafter
    """

    @staticmethod
    def get_order_list(user):
        orders = Order.objects\
            .exclude(
                Q(orderdocument__type=OrderDocument.DOCUMENT_FACTORY_PLAN) &
                Q(orderdocument__type=OrderDocument.DOCUMENT_CHASSIS_PLAN)
            )\
            .filter(
                order_cancelled__isnull=True,
                build__drafter=user,
            ).annotate(action_name=Value('Prepare factory and chassis plans', CharField()))\
            .extra(select={'days_waiting': 'DATEDIFF(NOW(), special_features_changed_at)'})\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return [o for o in orders if o.get_customer_plan_status() == Order.STATUS_APPROVED and o.get_finalization_status() == Order.STATUS_APPROVED]


class PlansWaitingSignOffTodo(BaseTodoAction):
    """
    Orders with customer plan waiting for customer sign off
    For Dealer Sales Representative and Dealer Principal
    """

    @staticmethod
    def get_order_list(user):

        try:
            user.dealershipuser
        except user.DoesNotExist:
            return Order.objects.none()

        orders = Order.objects.filter(
            Q(dealership_id__in=user.dealershipuser.get_dealership_principal_ids()) | Q(customer_manager=user),
            order_cancelled__isnull=True,
        )\
            .annotate(action_name=Value('Sign Off', CharField()))\
            .extra(select={'days_waiting': 'DATEDIFF(NOW(), customer_plan_changed_at)'})\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return [o for o in orders if o.get_customer_plan_status() == Order.STATUS_PENDING]


class RejectedPlansTodo(BaseTodoAction):
    """
    Orders rejected customer plan
    For assigned drafter
    """

    @staticmethod
    def get_order_list(user):
        orders = Order.objects.filter(
            build__drafter=user,
            order_cancelled__isnull=True,
        )\
            .annotate(action_name=Value('Re-draft plans', CharField()))\
            .extra(select={'days_waiting': 'DATEDIFF(NOW(), customer_plan_rejected_at)'})\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return [o for o in orders if o.get_customer_plan_status() == Order.STATUS_REJECTED and o.get_finalization_status() == Order.STATUS_APPROVED]


class UnmetConditionsTodo(BaseTodoAction):
    """
    Orders with subject-to clause that have not been fulfilled
    For Customer Manager
    """

    @staticmethod
    def get_order_list(user):
        try:
            user.dealershipuser
        except user.DoesNotExist:
            return Order.objects.none()

        return Order.objects\
            .exclude(
                orderconditions__details=''
            )\
            .filter(
                order_cancelled__isnull=True,
                customer_manager=user,
                orderconditions__fulfilled=False,
            ).annotate(action_name=Value('Check and fulfill conditions', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

# Client has requested the removal of these items from to do list; however given the nature of client
#  we're keeping the original code here for the convenience should they decide to roll it back
'''
class ReadyForFinalisationTodo(BaseTodoAction):
    """
    Orders with special features approved and all selection made
    For Customer Manager
    """

    @staticmethod
    def get_order_list(user):
        if not user.has_perm('orders.finalize_order'):
            return Order.objects.none()

        orders = Order.objects.filter(
            order_cancelled__isnull=True,
            series__isnull=False,
            has_missing_selections=False,
            order_submitted__isnull=False,
        ).filter(
            Q(orderconditions__details='') | Q(orderconditions__fulfilled=True)
        )\
            .annotate(action_name=Value('Ready for finalisation', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return [
            o for o in orders
            if o.get_special_features_status() in (Order.STATUS_APPROVED, Order.STATUS_NONE) and
                o.get_finalization_status() in (Order.STATUS_REJECTED, Order.STATUS_NONE)
        ]
'''

class WaitingPlannedQcDateTodo(BaseTodoAction):
    """
    Orders with factory and chassis plans without a qc_date_planned and after build_date - 21 days
    For members of Transport Team
    """

    @staticmethod
    def get_order_list(user):
        if not user.has_perm('delivery.is_transport_team'):
            return []

        order_ids_with_factory = set(Order.objects.filter(orderdocument__type=OrderDocument.DOCUMENT_FACTORY_PLAN).values_list('id', flat=True))
        order_ids_with_chassis = set(Order.objects.filter(orderdocument__type=OrderDocument.DOCUMENT_CHASSIS_PLAN).values_list('id', flat=True))
        order_ids_with_both_docs = order_ids_with_factory & order_ids_with_chassis

        cutoff_time = timezone.now().date() + timedelta(days=21)

        orders = Order.objects.filter(
            order_cancelled__isnull=True,
            build__build_date__isnull=False,
            build__build_date__lte=cutoff_time,
            build__qc_date_planned__isnull=True,
            id__in=order_ids_with_both_docs
        )\
            .annotate(action_name=Value('Enter Planned QC Date', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return orders


class WaitingActualQcDateTodo(BaseTodoAction):
    """
    Orders with qc_date_planned and after qc_date_planned - 1 days and without an qc_date_actual
    For members of Transport Team
    """

    @staticmethod
    def get_order_list(user):
        if not user.has_perm('delivery.is_transport_team'):
            return []

        one_days_time = timezone.now().date() + timedelta(days=1)

        orders = Order.objects.filter(
            order_cancelled__isnull=True,
            build__qc_date_planned__isnull=False,
            build__qc_date_planned__lte=one_days_time,
            build__qc_date_actual__isnull=True,
        )\
            .annotate(action_name=Value('Enter Actual QC Date', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return orders


# Get the orders That are to be Verified By The Senior Designer
class WaitingSeniorTodo(BaseTodoAction):
    """
    Orders with factory and chassis plans that are waiting to be verified by Senior Designer to be shown here  
    For members of VIN & Weights Team
    """

    @staticmethod
    def get_order_list(user):
        if not user.has_perm('delivery.is_vin_weight_team'):
            return []

        order_ids_with_factory = set(Order.objects.filter(orderdocument__type=OrderDocument.DOCUMENT_FACTORY_PLAN).values_list('id', flat=True))
        order_ids_with_chassis = set(Order.objects.filter(orderdocument__type=OrderDocument.DOCUMENT_CHASSIS_PLAN).values_list('id', flat=True))
        order_ids_with_both_docs = order_ids_with_factory & order_ids_with_chassis
        # cutoff_time = timezone.now().date() + timedelta(days=21)

        orders = Order.objects.filter(
            build__vin_number__isnull=True,
            order_cancelled__isnull=True,
            build__build_date__isnull=False,
            # build__build_date__lte=cutoff_time,
            ordertransport__senior_designer_verfied_date__isnull = True,
            ordertransport__purchase_order_raised_date__isnull = True,
            id__in=order_ids_with_both_docs,
        )\
            .annotate(action_name=Value('Senior Designer to Verify', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return orders


# Get the orders for Purchase Order to Be Raised
class PurchaseOrderTodo(BaseTodoAction):
    """
    Orders with Senior Engineer Verified  are waiting for Purchase Order to Raised and shown here  
    For members of VIN & Weights Team
    """

    @staticmethod
    def get_order_list(user):
        if not user.has_perm('delivery.is_vin_weight_team'):
            return []

        order_ids_with_factory = set(Order.objects.filter(orderdocument__type=OrderDocument.DOCUMENT_FACTORY_PLAN).values_list('id', flat=True))
        order_ids_with_chassis = set(Order.objects.filter(orderdocument__type=OrderDocument.DOCUMENT_CHASSIS_PLAN).values_list('id', flat=True))
        order_ids_with_both_docs = order_ids_with_factory & order_ids_with_chassis
        # cutoff_time = timezone.now().date() + timedelta(days=21)

        orders = Order.objects.filter(
            build__vin_number__isnull=True,
            order_cancelled__isnull=True,
            build__build_date__isnull=False,
            ordertransport__senior_designer_verfied_date__isnull = False,
            ordertransport__purchase_order_raised_date__isnull = True,
            # build__build_date__lte=cutoff_time,
            # id__in=order_ids_with_both_docs,
        )\
            .annotate(action_name=Value('Raise Purchase Order', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer','ordertransport')

        return orders


class WaitingVinTodo(BaseTodoAction):
    """
    Orders with factory and chassis plans without a vin_number value and after build_date - 7 days
    For members of VIN & Weights Team
    """

    @staticmethod
    def get_order_list(user):
        if not user.has_perm('delivery.is_vin_weight_team'):
            return []

        order_ids_with_factory = set(Order.objects.filter(orderdocument__type=OrderDocument.DOCUMENT_FACTORY_PLAN).values_list('id', flat=True))
        order_ids_with_chassis = set(Order.objects.filter(orderdocument__type=OrderDocument.DOCUMENT_CHASSIS_PLAN).values_list('id', flat=True))
        order_ids_with_both_docs = order_ids_with_factory & order_ids_with_chassis
        # cutoff_time = timezone.now().date() + timedelta(days=21)


        orders = Order.objects.filter(
            build__vin_number__isnull=True,
            order_cancelled__isnull=True,
            build__build_date__isnull=False,
            # build__build_date__lte=cutoff_time,
            id__in=order_ids_with_both_docs,
            ordertransport__senior_designer_verfied_date__isnull = False,
            ordertransport__purchase_order_raised_date__isnull = False,
        )\
            .annotate(action_name=Value('Enter VIN', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return orders


class WaitingWeightTodo(BaseTodoAction):
    """
    Orders with qc_date_actual and without a weights value
    For members of VIN & Weights Team
    """

    @staticmethod
    def get_order_list(user):
        if not user.has_perm('delivery.is_vin_weight_team'):
            return []

        order_ids_with_factory = set(Order.objects.filter(orderdocument__type=OrderDocument.DOCUMENT_FACTORY_PLAN).values_list('id', flat=True))
        order_ids_with_chassis = set(Order.objects.filter(orderdocument__type=OrderDocument.DOCUMENT_CHASSIS_PLAN).values_list('id', flat=True))
        order_ids_with_both_docs = order_ids_with_factory & order_ids_with_chassis

        orders = Order.objects.filter(
            Q(build__weight_tare__isnull=True) |
            Q(build__weight_atm__isnull=True) |
            Q(build__weight_tow_ball__isnull=True) |
            Q(build__weight_tyres__isnull=True) |
            Q(build__weight_chassis_gtm__isnull=True) |
            Q(build__weight_gas_comp__isnull=True) |
            Q(build__weight_payload__isnull=True),
            build__qc_date_actual__isnull=False,
            order_cancelled__isnull=True,
            id__in=order_ids_with_both_docs,
        )\
            .annotate(action_name=Value('Enter Weights', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return orders


class WaitingActualDispatchDateTodo(BaseTodoAction):
    """
    Orders with qc_date_planned and after qc_date_planned - 1 days and without an dispatch_date_actual
    For members of Transport Team
    """

    @staticmethod
    def get_order_list(user):
        if not user.has_perm('delivery.is_transport_team'):
            return []

        one_days_time = timezone.now().date() + timedelta(days=1)

        orders = Order.objects.filter(
            order_cancelled__isnull=True,
            build__qc_date_planned__isnull=False,
            build__qc_date_planned__lte=one_days_time,
            dispatch_date_actual__isnull=True,
        )\
            .annotate(action_name=Value('Enter Actual Dispatch Date', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return orders


class WaitingHandoverToDriverFormTodo(BaseTodoAction):
    """
    Orders with qc_date_planned and after qc_date_planned - 1 days and without an handover_to_driver_form
    For members of Transport Team
    """

    @staticmethod
    def get_order_list(user):
        if not user.has_perm('delivery.is_transport_team'):
            return []

        one_days_time = timezone.now().date() + timedelta(days=1)

        orders = Order.objects.filter(
            order_cancelled__isnull=True,
            build__qc_date_planned__isnull=False,
            build__qc_date_planned__lte=one_days_time,
        ).exclude(
            orderdocument__type=OrderDocument.DOCUMENT_HANDOVER_TO_DRIVER_FORM
        )\
            .annotate(action_name=Value('Upload Driver Handover Form', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return orders


class WaitingDealershipReceivedTodo(BaseTodoAction):
    """
    Orders with dispatch_date_actual without an received_date_dealership
    For Customer Manager
    """

    @staticmethod
    def get_order_list(user):
        orders = Order.objects.filter(
            customer_manager=user,
            order_cancelled__isnull=True,
            dispatch_date_actual__isnull=False,
            received_date_dealership__isnull=True,
        )\
            .annotate(action_name=Value('Enter VAN Received Date', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return orders


class WaitingHandoverToDealershipFormTodo(BaseTodoAction):
    """
    Orders with dispatch_date_actual without an handover_to_dealership_form
    For Customer Manager
    """

    @staticmethod
    def get_order_list(user):
        orders = Order.objects.filter(
            customer_manager=user,
            order_cancelled__isnull=True,
            dispatch_date_actual__isnull=False,
        ).exclude(
            orderdocument__type=OrderDocument.DOCUMENT_HANDOVER_TO_DEALERSHIP_FORM
        )\
            .annotate(action_name=Value('Upload Driver Handover To Dealership Form', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return orders


class WaitingCustomerDeliveryDateTodo(BaseTodoAction):
    """
    Orders with received_date_dealership without an delivery_date_customer
    For Customer Manager
    """

    @staticmethod
    def get_order_list(user):
        orders = Order.objects.filter(
            customer_manager=user,
            order_cancelled__isnull=True,
            delivery_date_customer__isnull=True,
            customer__isnull=False,
            orderdocument__type=OrderDocument.DOCUMENT_HANDOVER_TO_DEALERSHIP_FORM,
        )\
            .annotate(action_name=Value('Enter Customer Delivery Date', CharField()))\
            .select_related('build__build_order', 'dealership', 'orderseries__series__model', 'customer')

        return orders



# Generate the list from all classes defined here that inherit from BaseTodoAction
TODO_ACTION_LIST = []

for name, obj in inspect.getmembers(sys.modules[__name__]):
    if inspect.isclass(obj) and not name == 'BaseTodoAction' and issubclass(obj, BaseTodoAction):
        TODO_ACTION_LIST.append(obj)
