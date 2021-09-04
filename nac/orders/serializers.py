import mimetypes
from os import path
import re

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from audit.models import Audit
from audit.models import AuditField
from caravans.models import SeriesSKU
from caravans.serializers import RuleSerializer
from caravans.serializers import SKUSerializer
from customers.serializers import CustomerSerializer
from orders.models import AfterMarketNote
from orders.models import Order
from orders.models import OrderConditions
from orders.models import OrderDocument
from orders.models import CertificateDeleted
from orders.models import OrderNote
from orders.models import OrderSKU
from orders.models import Show
from orders.models import ShowSpecial
from orders.models import SpecialFeature
from production.models import Build
from production.models import BuildOrder
from schedule.models import OrderTransport
from orders.models import OrderSeries

DATE_FORMAT = re.compile(r'\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d\.\d{6}\+\d\d:\d\d')

class SpecialFeatureSerializer(serializers.ModelSerializer):
    document = serializers.SerializerMethodField()

    def get_document(self, instance):
        if not instance.document:
            return None

        return {
            'name': instance.document.name.split('/')[-1],
            'url': instance.document.url,
            'type': mimetypes.MimeTypes().guess_type(instance.document.name)[0],
        }

    class Meta:
        model = SpecialFeature
        fields = (
            'id',
            'order',
            'sku_category',
            'customer_description',
            'retail_price',
            'wholesale_price',
            'document',
            'factory_description',
            'approved',
            'reject_reason',
        )


class OrderConditionSerializer(serializers.ModelSerializer):

    class Meta:
        model = OrderConditions
        fields = (
            'id',
            'details',
            'fulfilled',
        )


class AfterMarketNoteSerializer(serializers.ModelSerializer):

    class Meta:
        model = AfterMarketNote
        fields = (
            'id',
            'note',
        )


class OrderSerializer(serializers.ModelSerializer):
    model = serializers.IntegerField(source='orderseries.series.model.id')
    series = serializers.SerializerMethodField()
    series_description = serializers.SerializerMethodField()
    series_code = serializers.SerializerMethodField()
    series_retail_price = serializers.FloatField(source='orderseries.retail_price')
    series_wholesale_price = serializers.FloatField(source='orderseries.wholesale_price')
    series_cost_price = serializers.FloatField(source='orderseries.cost_price')
    production_month = serializers.SerializerMethodField()
    production_start_date = serializers.SerializerMethodField()
    dealership_name = serializers.CharField(source='dealership.name')
    dealer_sales_rep_name = serializers.CharField(source='dealer_sales_rep.name')
    customer_manager_name = serializers.CharField(source='customer_manager.name')
    show_special_id = serializers.IntegerField(source='ordershowspecial.special.id')
    special_features = SpecialFeatureSerializer(source='specialfeature_set', many=True)
    order_stage_details = serializers.SerializerMethodField()
    customer = CustomerSerializer()
    orderconditions = OrderConditionSerializer()
    aftermarketnote = AfterMarketNoteSerializer()
    is_expired = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()
    customer_plans_approved = serializers.SerializerMethodField()
    special_features_approved = serializers.SerializerMethodField()
    order_converted = serializers.DateField(format=settings.FORMAT_DATE)
    order_type = serializers.SerializerMethodField()

    def get_is_expired(self, order):
        return order.is_expired()

    def get_order_stage_details(self, order):
        return order.get_order_stage_details()

    def get_items(self, order):
        "Returns the selected item per department"
        is_order_finalized = order.get_finalization_status() == Order.STATUS_APPROVED

        skus = {}
        for order_sku in order.ordersku_set.select_related('sku').all():
            sku = SKUSerializer(order_sku.sku, availability_type=order_sku.base_availability_type).data
            # When order is finalised, use the price information recorded against the OrderSku
            if is_order_finalized:
                sku['retail_price'] = order_sku.retail_price
                sku['wholesale_price'] = order_sku.wholesale_price
                sku['cost_price'] = order_sku.cost_price
            skus[order_sku.sku.sku_category_id] = sku

        return skus

    def get_customer_plans_approved(self, order):
        return order.get_customer_plan_status() == Order.STATUS_APPROVED

    def get_special_features_approved(self, order):
        return order.get_special_features_status() == Order.STATUS_APPROVED

    def get_series_description(self, order):
        return order.get_series_description()

    def get_order_type(self, order):
        return order.get_order_type()

    def get_series_code(self, order):
        return order.get_series_code()

    def get_series(self, order):
        return order.orderseries.series_id if hasattr(order, 'orderseries') else None

    def get_production_month(self, order):
        month = order.get_production_month()
        if month != '':
            month = month.strftime(settings.FORMAT_DATE_MONTH)
        return month

    def get_production_start_date(self, order):
        return order.get_production_start_date()

    class Meta:
        model = Order
        fields = (
            'id',
            'order_type',
            'series',
            'model',
            'custom_series_name',
            'custom_series_code',
            'series_description',
            'series_code',
            'series_retail_price',
            'series_wholesale_price',
            'series_cost_price',
            'production_month',
            'production_start_date',
            'dealership',
            'dealership_name',
            'dealer_sales_rep_name',
            'customer_manager_name',
            'delivery_date',
            'order_stage_details',
            'weight_estimate_disclaimer_checked',
            'custom_tare_weight_kg',
            'custom_ball_weight_kg',
            'show_special_id',
            'special_features',
            'customer',
            'price_adjustment_cost',
            'price_adjustment_wholesale',
            'price_adjustment_wholesale_comment',
            'price_adjustment_retail',
            'dealer_load',
            'trade_in_write_back',
            'trade_in_comment',

            'after_sales_wholesale',
            'after_sales_retail',
            'after_sales_description',

            'price_comment',
            'show',
            'orderconditions',
            'aftermarketnote',
            'is_expired',
            'has_missing_selections',
            'items',
            'customer_plans_approved',
            'chassis',
            'appretail_opportunity_no',
            'special_features_approved',
            'is_order_converted',
            'order_converted',

            'salesforce_sync_error',
        )
        read_only_fields = (
            'order_stage_details',
            'order_type',
            'salesforce_sync_error',
        )


class LocalizedDateTimeField(serializers.DateTimeField):
    def to_representation(self, value):
        value = timezone.localtime(value)
        return super(LocalizedDateTimeField, self).to_representation(value)

class OrderHistorySerializer(serializers.Serializer):
    notes = serializers.SerializerMethodField()
    action = serializers.SerializerMethodField()
    update_on = LocalizedDateTimeField(source='saved_on', format='%d/%b/%Y %H:%M:%S')
    update_by = serializers.SerializerMethodField()

    def sku_changed(fields_changed):
        return 'Feature Added' if int(fields_changed['base_availability_type'][1]) != SeriesSKU.AVAILABILITY_STANDARD else ''

    def get_cert_type(x):
        # the EGM thing's causing order_submitted to be updated twice. We only care for the first time.
        # print('Length ',len(x))
        # print( ' 0 ', x[0])
        # print(' 1 ' ,x[1])
        return 'Certificate Uploaded'

    def get_deleted_cert_type(x):
        # the EGM thing's causing order_submitted to be updated twice. We only care for the first time.
        # print('Length ',len(x))
        # print( ' 0 ', x[0])
        # print(' 1 ' ,x[1])
        return 'Certificate Deleted'

        # return 'Certificate Uploaded'
        # return 'Order Placed' if x[0] is None else ''
    def order_placed(x):
        # the EGM thing's causing order_submitted to be updated twice. We only care for the first time.
        return 'Order Placed' if x[0] is None else ''

    def order_cancelled(x):
        # just like order placed, EGM's updating this one as well....WHY?!
        return 'Order Cancelled' if x[0] is None else ''

    def f(desc, desc_set_alt='Set', desc_change_alt='Changed'):
        # shortened func names used here to improve the layout in matrix below.
        # returns a func that produces "Something Set" if the original value does not exist, otherwise "Something Changed"
        return lambda x: '%s %s' % (desc, desc_set_alt) if x[0] is None else '%s %s' % (desc, desc_change_alt)

    #For Hold caravans
    def f1(desc, desc_set_alt='Set'):
        # shortened func names used here to improve the layout in matrix below.
        # returns a func that produces "Something Set" 
        return lambda x: '%s %s' % (desc, desc_set_alt) #if x[0] is None else '%s %s' % (desc, desc_change_alt)

    #for production unit in orderseries
    def f2(desc, desc_change_alt='Changed to'):
        return lambda x: '%s %s' % (desc, desc_change_alt)

    def g(desc, key_field, alt_desc='', display_for_none='None'):
        # shortened func names used here to improve the layout in matrix below.
        # returns a func that produces a description (desc) based on the NEW value of key_field, and could optionally
        #   replaces the "None" with a preset string like "(Stock)".
        # if the original desc comes with two %s, then presence of alt_desc is assumed and alt_desc will be used to handle
        #   the case where one of the value is None.
        def replace_with_none(string):
            return string if string is not None else display_for_none
        if len(desc.replace('%s', '')) == len(desc) - 4:
            return lambda x: alt_desc % replace_with_none(x[key_field][1]) if x[key_field][0] in [None, 'None'] else desc % (x[key_field][0], replace_with_none(x[key_field][1]))
        return lambda x: desc % replace_with_none(x[key_field][1])

    def h(fields_changed):
        # These are special items that, when changed, *some* of them might get changed at once. Client requested them to be logged as a single entry.
        note = ''
        for key_field in ['weight_tare', 'weight_atm', 'weight_tow_ball', 'weight_tyres', 'weight_chassis_gtm', 'weight_gas_comp', 'weight_payload']:
            if key_field in fields_changed:
                if fields_changed[key_field][0] in [None, 'None']:
                    old_value = None
                else:
                    old_value = str(fields_changed[key_field][0])

                new_value = fields_changed[key_field][1]

                note += key_field.replace('weight_', '').replace('_', ' ').capitalize()
                if old_value is not None:
                    note += ': %s => %s' % (old_value, new_value)
                else:
                    note += ': %s' % (new_value)
                note += '\n'
        return note

    actionlist = [
        (OrderSKU,      Audit.ACTION_UPDATED, 'sku',                    'Feature Changed',          g('Old: %s\nNew: %s', 'sku')),
        (OrderSKU,      Audit.ACTION_CREATED, '',                       sku_changed,                g('%s', 'sku')),

        (OrderDocument, Audit.ACTION_CREATED, lambda x: x.get_type_display() == 'Customer Plan',  'Plan Uploaded', 'Customer Plan Uploaded'),
        (OrderDocument, Audit.ACTION_CREATED, lambda x: x.get_type_display() == 'Factory Plan',   'Plan Uploaded', 'Factory Plan Uploaded'),
        (OrderDocument, Audit.ACTION_CREATED, lambda x: x.get_type_display() == 'Chassis Plan',   'Plan Uploaded', 'Chassis Plan Uploaded'),
        (OrderDocument, Audit.ACTION_CREATED, lambda x: x.get_type_display() == 'Handover to driver form', 'Form Uploaded', 'Handover to driver form Uploaded'),
        (OrderDocument, Audit.ACTION_CREATED, lambda x: x.get_type_display() == 'Handover to dealership form', 'Form Uploaded', 'Handover to dealership form Uploaded'),

        
        (OrderDocument, Audit.ACTION_CREATED, 'cert_title',  get_cert_type   ,  g(' %s ', 'cert_title')),
        

        (Order,         Audit.ACTION_UPDATED, 'order_finalization_cancelled_at', 'Order Lock Cancelled', g('Reason: %s', 'order_finalization_cancel_reason')),

        # These are special items that, when changed, *some* of them might get changed at once. Client requested them to be logged as a single entry.
        (Build,         Audit.ACTION_UPDATED, 'weight_tare',            f('Build Weight'), h),
        (Build,         Audit.ACTION_UPDATED, 'weight_atm',             f('Build Weight'), h),
        (Build,         Audit.ACTION_UPDATED, 'weight_tow_ball',        f('Build Weight'), h),
        (Build,         Audit.ACTION_UPDATED, 'weight_tyres',           f('Build Weight'), h),
        (Build,         Audit.ACTION_UPDATED, 'weight_chassis_gtm',     f('Build Weight'), h),
        (Build,         Audit.ACTION_UPDATED, 'weight_gas_comp',        f('Build Weight'), h),
        (Build,         Audit.ACTION_UPDATED, 'weight_payload',         f('Build Weight'), h),

        (Order,         Audit.ACTION_UPDATED, 'received_date_dealership', f('Dealership Received'), g('Old: %s\nNew: %s', 'received_date_dealership', '%s')),
        (Order,         Audit.ACTION_UPDATED, 'delivery_date_customer', f('Customer Delivery Date'), g('Old: %s\nNew: %s', 'delivery_date_customer', '%s')),
        (Order,         Audit.ACTION_UPDATED, 'dispatch_date_planned',  f('Planned Dispatch Date'), g('Old: %s\nNew: %s', 'dispatch_date_planned', '%s')),
        
        (Order,         Audit.ACTION_UPDATED, 'dealership', f('Dealership'), g('Old: %s\nNew: %s', 'dealership', '%s')),


        #OrderTransport audit history update with old and new value
        (OrderTransport,         Audit.ACTION_UPDATED, 'senior_designer_verfied_date',  f('Senior Designer Verified Date'), g('Old: %s\nNew: %s', 'senior_designer_verfied_date', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'purchase_order_raised_date',  f('Purchase Order Date Raised'), g('Old: %s\nNew: %s', 'purchase_order_raised_date', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'actual_production_date',  f('Actual Production Date'), g('Old: %s\nNew: %s', 'actual_production_date', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'actual_production_comments',  f('Production Comments'), g('Old: %s\nNew: %s', 'actual_production_comments', '%s')),

        (OrderTransport,         Audit.ACTION_UPDATED, 'qc_comments',  f('QC Comments'), g('Old: %s\nNew: %s', 'qc_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'final_qc_date',  f('QC Date'), g('Old: %s\nNew: %s', 'final_qc_date', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'final_qc_comments',  f('QC Comments'), g('Old: %s\nNew: %s', 'final_qc_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'dispatch_comments',  f('Dispatch Comments'), g('Old: %s\nNew: %s', 'dispatch_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'watertest_date',  f('Water Test Date'), g('Old: %s\nNew: %s', 'watertest_date', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'watertest_comments',  f('Water Test Comments'), g('Old: %s\nNew: %s', 'watertest_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'weigh_bridge_date',  f('Weigh Bridge Date'), g('Old: %s\nNew: %s', 'weigh_bridge_date', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'weigh_bridge_comments',  f('Weigh Bridge Comments'), g('Old: %s\nNew: %s', 'weigh_bridge_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'detailing_date',  f('Detailing Date'), g('Old: %s\nNew: %s', 'detailing_date', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'detailing_comments',  f('Detailing Comments'), g('Old: %s\nNew: %s', 'detailing_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'chassis_section',  f('Chassis Section Date'), g('Old: %s\nNew: %s', 'chassis_section', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'email_sent',  'Email Sent', g('Email Sent On : %s', 'email_sent')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'collection_comments',  'Collection Comments', g('Collection Comments Changed : %s', 'collection_comments')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'chassis_section_comments',  f('Chassis Section Comments'), g('Old: %s\nNew: %s', 'chassis_section_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'building',  f('Building Date'), g('Old: %s\nNew: %s', 'building', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'building_comments',  f('Building Comments'), g('Old: %s\nNew: %s', 'building_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'prewire_section',  f('Prewire Section Date'), g('Old: %s\nNew: %s', 'prewire_section', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'prewire_comments',  f('Prewire Comments'), g('Old: %s\nNew: %s', 'prewire_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'plumbing_date',  f('Plumbing Section Date'), g('Old: %s\nNew: %s', 'plumbing_date', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'plumbing_comments',  f('Plumbing Comments'), g('Old: %s\nNew: %s', 'plumbing_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'aluminium',  f('Aluminium Date'), g('Old: %s\nNew: %s', 'aluminium', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'aluminium_comments',  f('Aluminium Comments'), g('Old: %s\nNew: %s', 'aluminium_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'finishing',  f('Finishing Date'), g('Old: %s\nNew: %s', 'finishing', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'finishing_comments',  f('Finishing Comments'), g('Old: %s\nNew: %s', 'finishing_comments', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'collection_date',   f('Collection Date'),      g('Old: %s\nNew: %s', 'collection_date', '%s')),
        (OrderTransport,         Audit.ACTION_UPDATED, 'hold_caravans',  f1('Holding Caravans'), g('%s', 'hold_caravans', '%s')),



        (OrderSeries,         Audit.ACTION_UPDATED, 'production_unit',        f2('Schedule Unit'),       g('%s', 'production_unit', '%s')),

        
        (Build,         Audit.ACTION_UPDATED, 'build_date',             'Production Month Changed', g('Changed from: %s\nto New: %s', 'build_date', '%s')),
        (BuildOrder,    Audit.ACTION_UPDATED, 'build_order',            f('Build Order Changed'),   g('Old: %s\nNew: %s', 'build_order', '%s')),
        (Build,         Audit.ACTION_UPDATED, 'qc_date_planned',        f('Planned QC Date'),       g('Old: %s\nNew: %s', 'qc_date_planned', '%s')),
        (Order,         Audit.ACTION_UPDATED, 'dispatch_date_actual',   f('Actual Dispatch Date'),  g('Old: %s\nNew: %s', 'dispatch_date_actual', '%s')),
        (Build,         Audit.ACTION_UPDATED, 'qc_date_actual',         f('Actual QC Date'),        g('Old: %s\nNew: %s', 'qc_date_actual', '%s')),
        (Build,         Audit.ACTION_UPDATED, 'vin_number',             f('VIN Number'),            g('Old: %s\nNew: %s', 'vin_number', '%s')),
        (Build,         Audit.ACTION_UPDATED, 'drafter',                f('Drafter', 'Assigned'),   g('Previous: %s\nCurrent: %s', 'drafter', '%s')),
        (Order,         Audit.ACTION_UPDATED, 'chassis',                'Chassis Number Set',       g('%s', 'chassis')),
        (Order,         Audit.ACTION_UPDATED, 'order_cancelled',        order_cancelled,            g('Reason: %s', 'order_cancelled_reason')),
        (Order,         Audit.ACTION_UPDATED, 'order_finalized_at',     'Order Locked',             ''),
        (Order,         Audit.ACTION_UPDATED, 'deposit_paid_amount',    'Deposit Paid',             g('Deposit paid: $%s', 'deposit_paid_amount')),
        (Order,         Audit.ACTION_UPDATED, 'order_submitted',        order_placed,               ''),
        (Order,         Audit.ACTION_UPDATED, 'order_requested',        'Order Requested',          ''),
        (Order,         Audit.ACTION_UPDATED, 'customer',               'Customer Changed',         g('Old: %s\nNew: %s', 'customer', 'Old: (STOCK)\nNew: %s', display_for_none='(STOCK)')),
        (OrderSeries,         Audit.ACTION_UPDATED, 'model_id',         'Model Changed',          g('Old: %s\nNew: %s', 'model_id', 'Model: %s')),
        (OrderSeries,         Audit.ACTION_UPDATED, 'series',           'Series Changed',           g('Old: %s\nNew: %s', 'series','Series: %s')),

        (Order,         Audit.ACTION_UPDATED, 'price_adjustment_wholesale', 'Costings',             g('Wholesale Price Adjustment changed from $%s to $%s', 'price_adjustment_wholesale', 'Wholesale Price Adjustment set to $%s')),
        (Order,         Audit.ACTION_UPDATED, 'price_adjustment_retail',    'Costings',             g('Retail Price Adjustment changed from $%s to $%s', 'price_adjustment_retail', 'Retail Price Adjustment set to $%s')),
        (Order,         Audit.ACTION_UPDATED, 'dealer_load',                'Costings',             g('Dealer Load Price changed from $%s to $%s', 'dealer_load', 'Dealer Load Price set to $%s')),
        (Order,         Audit.ACTION_UPDATED, 'trade_in_write_back',        'Costings',             g('Trade-in Writeback changed from $%s to $%s', 'trade_in_write_back', 'Trade-in Writeback set to $%s')),
        (Order,         Audit.ACTION_UPDATED, 'after_sales_wholesale',      'Costings',             g('After Sales Wholesale changed from $%s to $%s', 'after_sales_wholesale', 'After Sales Wholesale set to $%s')),
        (Order,         Audit.ACTION_UPDATED, 'after_sales_retail',         'Costings',             g('After Sales Retail changed from $%s to $%s', 'after_sales_retail', 'After Sales Retail set to $%s')),
        (Order,         Audit.ACTION_UPDATED, 'after_sales_description',    'Costings',             g('After Sales Description changed from [%s] to [%s]', 'after_sales_description', 'After Sales Description set to [%s]')),

        (OrderConditions, Audit.ACTION_UPDATED, 'details',              'Subject To Changed',       g('Subject To condition set to [%s]', 'details')),
        (OrderConditions, Audit.ACTION_UPDATED, 'fulfilled',            'Subject To Changed',       g('Subject To ready flag set to [%s]', 'fulfilled')),

        (AfterMarketNote, Audit.ACTION_UPDATED, 'note',                 'After Market Note',        g('After Market Note set to [%s]', 'note')),


        (OrderNote,     Audit.ACTION_CREATED, '',                       'User Comment',             ''),
        (Order,         Audit.ACTION_CREATED, '',                       'Order Created',            g('Customer: %s', 'customer', display_for_none='(STOCK)')),
    ]


    def get_action(self, obj):
        if isinstance(obj.content_object, OrderNote):
            if obj.use_content_repr_as_action:
                return obj.content_repr

        fields_changed = {}
        for f in obj.auditfield_set.all():
            fields_changed[f.name] = (f.changed_from, f.changed_to)

        for class_type, action_type, key, desc, note in self.actionlist:
            if action_type == obj.type and isinstance(obj.content_object, class_type):
                if key == '':
                    if type(desc) == str:
                        return desc
                    else:
                        return desc(fields_changed)
                if type(key) == str and key in fields_changed:
                    if type(desc) == str:
                        return desc
                    else:
                        return desc(fields_changed[key])
                if type(key) != str and key(obj.content_object):
                    return desc
        return ''


    def get_notes(self, obj):
        if isinstance(obj.content_object, OrderNote):
            note = []
            if obj.content_object.note is not None:
                note += obj.content_object.note.split('\n')
            if obj.content_object.file not in [None, '']:
                note += ['<a href=%s>Attachment</a>' % obj.content_object.file.url]
            return note

        fields_changed = {}
        for f in obj.auditfield_set.all():
            fields_changed[f.name] = (f.changed_from, f.changed_to)

        notes = []

        for class_type, action_type, key, desc, note in self.actionlist:
            if action_type == obj.type and isinstance(obj.content_object, class_type):
                try:
                    if key == '':
                        if type(note) == str:
                            notes += note.split('\n')
                        else:
                            notes += note(fields_changed).split('\n')
                        break
                    if type(key) == str and key in fields_changed:
                        if type(note) == str:
                            notes += note.split('\n')
                        else:
                            notes += note(fields_changed).split('\n')

                        # costings and subject-tos are special cases in that all "costing" items / subject-to items, unlike others, can be grouped together in one audit
                        # thus if we find one costing, continue the search and dont break yet.
                        if desc != 'Costings' and desc != 'Subject To Changed':
                            break

                    if type(key) != str and key(obj.content_object):
                        notes += note.split('\n')
                        break
                except KeyError: # EGM sometimes "duplicate" entry but without fully replicating them leaving desired audit_field not existing on the audit rec
                    pass

        return notes

    def get_update_by(self, obj):
        return obj.saved_by.get_full_name() if obj.saved_by is not None else ''


class ShowSpecialSerializer(serializers.ModelSerializer):
    rules = RuleSerializer(many=True)

    class Meta:
        model = ShowSpecial
        fields = (
            'id',
            'name',
            'description',
            'availability_description',
            'rules',
            'normal_price',
            'price',
            'tac_url',
        )


class ShowSerializer(serializers.ModelSerializer):

    class Meta:
        model = Show
        fields = (
            'id',
            'name',
            'start_date',
            'end_date',
        )
