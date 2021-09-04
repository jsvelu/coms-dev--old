
from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.urls import reverse_lazy
from django.db.models import Count
from django.http.response import HttpResponse
from django.template import loader
from django.template.context import Context
from django.utils import timezone
from django.views.generic import View
from django.views.generic.edit import FormView
from django_tables2.config import RequestConfig
from rules.contrib.views import PermissionRequiredMixin
from django.shortcuts import render

from caravans.models import SeriesPhoto
from caravans.models import SeriesSKU
from caravans.models import SKUCategory
from caravans.models import Supplier
from newage.models import ArchiveFile
from newage.utils import PrintableMixin
from orders.forms import BomForm
from orders.models import Order
from orders.models import OrderSKU
from orders.models import SpecialFeature
from orders.tables import BomOrderListTable


class BillOfMaterialsView(FormView):
    template_name = 'orders/bom.html'
    form_class = BomForm
    success_url = reverse_lazy('orders:bom')
    permission_required = 'orders.create_order'

    def get_form_kwargs(self):
        kwargs = {
        }
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
        return kwargs

    def get_context_data(self, **kwargs):
        context = super(BillOfMaterialsView, self).get_context_data(**kwargs)
        context['help_code'] = 'bill_of_materials'
        return context

    def form_invalid(self, form):
        return super(BillOfMaterialsView, self).form_invalid(form)

    def form_valid(self, form, **kwargs):
        context = self.get_context_data(**kwargs)

        start_date = datetime.strptime(self.request.POST.get('start_date'), settings.FORMAT_DATE_ISO)
        end_date = datetime.strptime(self.request.POST.get('end_date'), settings.FORMAT_DATE_ISO)

        supplier_id = self.request.POST.get('hdn_supplier_tab')

        if self.request.POST.get('btn_action') == 'show_report':
            orders = Order.objects.filter(order_date__gte=start_date).filter(order_date__lte=end_date)
            # .filter(dealer_sales_rep=self.request.user) << TODO uncomment after testing

            order_table = BomOrderListTable(orders)
            RequestConfig(self.request, paginate={'page': self.request.GET.get('page', 1), 'per_page': 50}).configure(order_table)
            context['order_table'] = order_table

            report = []
            suppliers = Supplier.objects.filter(is_bom_report_visible=True)
            for supplier in suppliers:
                supplier_data_list = OrderSKU.objects.filter(order__order_date__gte=start_date).filter(order__order_date__lte=end_date).\
                    filter(sku__supplier=supplier).prefetch_related('sku').values('order__chassis', 'sku__code', 'sku__description', 'sku__quantity')
                supplier_data_array = []
                for supplier_data_item in supplier_data_list:
                    supplier_data_row = type('', (), {})()
                    supplier_data_row.chassis = supplier_data_item['order__chassis']
                    supplier_data_row.code = supplier_data_item['sku__code']
                    supplier_data_row.description = supplier_data_item['sku__description']
                    supplier_data_row.count = supplier_data_item['sku__quantity']
                    supplier_data_array.append(supplier_data_row)

                if len(supplier_data_array) > 0:
                    report.append((supplier, supplier_data_array))

            context['report'] = report
            context['default_supplier_id'] = suppliers[0].pk
            context['form'] = form
            return self.render_to_response(context)

        if self.request.POST.get('btn_action') == 'ostendo_export':
            file_save_name = "bom_ostendo.txt"
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="' + file_save_name + '"'

            parts_deadline_date = (start_date + timedelta(days=settings.ORDERS_PARTS_DEADLINE_LEAD_DAYS)).strftime(settings.FORMAT_DATE)

            report_array = []
            # METERS_IN_A_FOOT = 0.3048
            # METERS_IN_AN_INCH = 0.0254
            MM_TO_METERS = 0.001

            report_data_list = OrderSKU.objects.filter(order__order_date__gte=start_date).filter(order__order_date__lte=end_date).\
                filter(sku__supplier_id=supplier_id)

            for report_data_item in report_data_list:
                report_data_row = type('', (), {})()
                report_data_row.id = report_data_item.id
                report_data_row.dealership = report_data_item.order.dealership.name
                report_data_row.chassis = report_data_item.order.chassis
                report_data_row.model = report_data_item.order.orderseries.series.model.name
                report_data_row.series = report_data_item.order.orderseries.series.name
                report_data_row.customer = report_data_item.order.customer.first_name + ' ' + report_data_item.order.customer.last_name
                report_data_row.length = report_data_item.order.orderseries.series.length_mm * MM_TO_METERS
                report_data_row.width = report_data_item.order.orderseries.series.width_mm * MM_TO_METERS 
                report_data_row.sku_code = report_data_item.sku.code
                report_data_row.quantity = report_data_item.sku.quantity
                report_data_row.order_date = report_data_item.order.order_date.strftime(settings.FORMAT_DATE)
                report_data_row.description = report_data_item.sku.description
                report_data_row.parent = report_data_item.sku.sku_category.parent.name

                report_array.append(report_data_row)

            template = loader.get_template('orders/bom_ostendo.txt')
            context = Context({
                'data': report_array,
                'parts_deadline': parts_deadline_date,
            })

            # archive it
            ArchiveFile.create(template.render(context), file_save_name, ArchiveFile.ARCHIVE_TYPE_BOM_OSTENDO)

            # render it
            response.write(template.render(context))
            return response

        if self.request.POST.get('btn_action') == 'csv_export':
            supplier = Supplier.objects.get(pk=supplier_id)

            file_save_name = 'order_list_' + supplier.name + '_' + \
                start_date.strftime(settings.FORMAT_DATE_ONEWORD) + '_' + end_date.strftime(settings.FORMAT_DATE_ONEWORD) + '_' + \
                timezone.now().strftime(settings.FORMAT_DATETIME_ONEWORD) + '.csv'

            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="' + file_save_name + '"'

            supplier_data_list = OrderSKU.objects.filter(order__order_date__gte=start_date).filter(order__order_date__lte=end_date).\
                filter(sku__supplier_id=supplier_id).values('order__chassis', 'sku__code', 'sku__description', 'sku__quantity').annotate(order_count=Count('sku_id'))
            supplier_data_array = []
            for supplier_data_item in supplier_data_list:
                supplier_data_row = type('', (), {})()
                supplier_data_row.chassis = supplier_data_item['order__chassis']
                supplier_data_row.code = supplier_data_item['sku__code']
                supplier_data_row.description = supplier_data_item['sku__description']
                supplier_data_row.count = supplier_data_item['sku__quantity'] * supplier_data_item['order_count']
                supplier_data_array.append(supplier_data_row)

            template = loader.get_template('orders/bom_csv.csv')
            context = Context({
                'data': supplier_data_array,
            })

            # archive it
            ArchiveFile.create(template.render(context), file_save_name, ArchiveFile.ARCHIVE_TYPE_BOM_CSV)

            # render it
            response.write(template.render(context))
            return response


class SpecView(PermissionRequiredMixin, PrintableMixin, View):
    template_name = 'orders/printable/specs.html'

    permission_required = 'orders.view_order'

    def get(self, request, *args, **kwargs):

        order = Order.objects.filter_by_visible_to(self.request.user).get(id=self.kwargs.get('order_id'))

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

        is_html = bool(request.GET.get('is_html'))
        context_data = {
            'order': order,
            'categories': categories,
            'company_name': settings.COMPANY_NAME,
            'production_notes': production_notes,
            'plans_completed': plans_completed,
        }

        # return self.render_printable(is_html, self.template_name, context_data, header_template="orders/printable/specs-header.html", pdf_options={"margin-top": "20mm", "orientation": "landscape"})
        return self.render_printable(is_html, self.template_name, context_data, header_template="orders/printable/specs-header.html", pdf_options={"margin-top": "20mm", "orientation": "landscape"})


class CustomerBrochureView(PermissionRequiredMixin, PrintableMixin, View):
    template_name = 'orders/printable/brochure.html'

    permission_required = 'orders.view_order'

    def get(self, request, order_id):

        order = Order.objects.filter_by_visible_to(self.request.user).get(id=order_id)

        plans_completed = order.get_customer_plan_status() >= Order.STATUS_PENDING

        categories = []
        top_level_categories_by_id = {}

        for skucategory in SKUCategory.top().skucategory_set.all().order_by('print_order'):
            category = {
                'name': skucategory.name,
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
                'name': ordersku.sku.name,
            }

            if plans_completed:
                # If a special feature is defined for this item, use the special feature description
                try:
                    special_feature = order.specialfeature_set.get(sku_category=ordersku.sku.sku_category)
                    special_feature_overrides.append(special_feature.id)
                    item = {
                        'red': True,
                        'name': special_feature.factory_description,
                    }
                except SpecialFeature.DoesNotExist:
                    pass

            if ordersku.base_availability_type == SeriesSKU.AVAILABILITY_OPTION:
                key = 'extras'

            top_level_categories_by_id[cat.id][key].append(item)

        if plans_completed:
            for special_feature in order.specialfeature_set.filter(sku_category__isnull=False).exclude(id__in=special_feature_overrides).prefetch_related('sku_category'):
                cat = special_feature.sku_category
                while cat.id not in top_level_categories_by_id:
                    cat = cat.parent

                top_level_categories_by_id[cat.id]['special_features'].append(special_feature.factory_description)

        try:
            main_photo = order.orderseries.series.seriesphoto_set.get(is_main_photo=True).photo
        except SeriesPhoto.DoesNotExist:
            main_photo = None

        is_html = bool(request.GET.get('is_html'))
        context_data = {
            'dealership': order.dealership,
            'customer': {
                'name': order.customer.name if order.customer else '(Stock)',
                'first_name': order.customer.first_name if order.customer else '',
            },
            'order': {
                'reference': order.id,
                'delivery_date': order.delivery_date,
                'series_description': order.get_series_description(),
            },

            'categories': categories,
            'photo_urls': {
                'main_photo': main_photo,
                'other': [seriesphoto.photo for seriesphoto in order.orderseries.series.seriesphoto_set.filter(is_main_photo=False, brochure_order__isnull=False).order_by('brochure_order')],
            },
            'dealer_rep_name': order.customer_manager.name,
            'is_html': is_html,
        }

        return self.render_printable(is_html, self.template_name, context_data)


class AutoCADExportView(PermissionRequiredMixin, PrintableMixin, View):
    template_name = 'orders/printable/autocad.html'

    permission_required = 'orders.print_for_autocad'

    def get(self, request, *args, **kwargs):
        is_html = bool(request.GET.get('is_html'))
        is_jpg = bool(request.GET.get('is_jpg'))

        order = Order.objects.filter_by_visible_to(self.request.user).get(id=self.kwargs.get('order_id'))

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

        availability_class_mapping = {
            SeriesSKU.AVAILABILITY_OPTION: 'extra',
            SeriesSKU.AVAILABILITY_UPGRADE: 'upgrade',
            SeriesSKU.AVAILABILITY_STANDARD: 'standard',
            SeriesSKU.AVAILABILITY_SELECTION: 'selection',
        }

        for ordersku in order.ordersku_set.all().prefetch_related('sku', 'sku__sku_category'):
            # If a SeriesSKU doesn't exist, we show it in green.
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
                'class': 'missing' if not seriessku else availability_class_mapping.get(ordersku.base_availability_type, 'standard'),
                'description': ordersku.sku.name,
            }

            # If a special feature is defined for this item, use the special feature description
            try:
                special_feature = order.specialfeature_set.get(sku_category=ordersku.sku.sku_category)
                special_feature_overrides.append(special_feature.id)
                item = {
                    'class': 'extra',
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
            selections = set([osku.sku.sku_category.id for
                              osku in order.ordersku_set.filter(base_availability_type__in=availability_types)])
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

        for special_feature in order.specialfeature_set.filter(sku_category__isnull=False).exclude(id__in=special_feature_overrides).prefetch_related('sku_category'):
            cat = special_feature.sku_category
            while cat.id not in top_level_categories_by_id:
                cat = cat.parent

            top_level_categories_by_id[cat.id]['special_features'].append(special_feature.factory_description)

        categories = [c for c in categories if c.get('features')]

        context_data = {
            'order': order,
            'production_notes': order.specialfeature_set.filter(sku_category__isnull=True).values_list('factory_description', flat=True),
            'categories': categories,
        }

        if is_jpg:
            return self.render_image(is_html, self.template_name, context_data, image_options={})
        else:
            return self.render_printable(is_html, self.template_name, context_data, pdf_options={"page-size": "A3"})


class InvoiceView(PermissionRequiredMixin, PrintableMixin, View):
    template_name = 'orders/printable/invoice.html'
    permission_required = 'orders.print_invoice'

    def get(self, request, *args, **kwargs):
        is_html = bool(request.GET.get('is_html'))
        # is_html = True

        order = Order.objects.filter_by_visible_to(self.request.user).get(id=self.kwargs.get('order_id'))

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
            'is_html': is_html,
            # 'is_html': True,
        }

        return self.render_printable(is_html, self.template_name, context_data)
        # return render(request, 'orders/printable/invoice.html', {'order': context_data})
