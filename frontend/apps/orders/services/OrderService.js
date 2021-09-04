import _ from 'lodash';

export default app => {

    app.factory('OrderService', (ApiService, AppSettings, Upload, $q) => {
        class Order {
            constructor() {
                this.resetOrder();
            }

            resetOrder() {
                this.resetOrderExceptCustomer();
                this.resetCustomer();
                this.resetPermissions();
            }

            resetOrderExceptCustomer() {
                this.resetOrderMainData();
                this.resetOrderItems();
            }

            resetOrderMainData() {
                this.id = null;
                this.model = null;
                this.series = null;
                this.custom_series_name = null;
                this.custom_series_code = null;
                this.series_description = null;
                this.series_code = null;
                this.production_month = null;
                this.production_start_date = null;
                this.modelSelection = null;
                this.seriesSelection = null;
                this.chassis = null;
                this.appretail_opportunity_no=null;
                this.order_type = null;
                this.delivery_date = null;
                this.dealership = null;
                this.dealer_sales_rep_name = null;
                this.customer_manager_name = null;
                this.order_stage_details = null;
                this.dealership_name = null;
                this.original = {};
                this.show_id = null;
                this.is_expired = false;
                this.base_order = null;
                this.customer_plans_approved = false;
                this.is_order_converted = false;
                this.order_converted = null;
                this.salesforce_sync_error = null;
            }

            resetOrderItems() {
                this.weight_estimate_disclaimer = false;
                this.custom_tare_weight = null;
                this.custom_ball_weight = null;
                this.show_special_id = null;
                this.price_adjustments = {
                    cost: 0,
                    wholesale: 0,
                    wholesale_comment: 0,
                    retail: 0,
                };
                this.after_sales = {
                    wholesale: 0,
                    retail: 0,
                    description: "",
                };
                this.dealer_load = 0;
                this.trade_in_write_back = 0;
                this.trade_in_comment = null;
                this.price_comment = null;
                this.show_special = null;
                this.orderconditions = {};
                this.aftermarketnote = {};
                this.has_missing_selections = true;
                this.items = {}; // key is the department, value is the list of items in the department
                this.special_features = [];
                this.special_features_approved = false;
                this.special_features_changed = false;
                this.price_changed = false;
            }

            resetCustomer() {
                this.customer = {
                    physical_address: {},
                    delivery_address: {},
                    postal_address: {},
                };
            }

            resetPermissions() {
                this.permissions = null;
            }

            isStageQuote() {
                // Duplicate implementation of nac.models.Order.is_quote()
                if (this.order_stage_details === undefined || this.order_stage_details === null) {
                    return true;
                }
                if (this.order_stage_details.number <= AppSettings.STAGE_QUOTE_SELECTIONS) {
                    return true;
                }
                return false;
            }

            isStageQuoteEditable() {
                if (this.permissions == null)
                    return true;

                return this.isStageQuote() && this.permissions.modify_order;
            }

            isCustomerVisible() {
                if (this.id == null) //means it is a new order > new order permission subsumes view customer details
                    return true;

                return this.permissions.list_customer;
            }

            isStageOrder() {
                return !this.isStageQuote();
            }

            isStockOrder(){
                return this.order_type == 'Stock';
            }

            isEditable() {
                if (!this.order_stage_details || this.isStockOrder()) {
                    return true;
                }
                if ((this.order_stage_details.code == 'QUOTE' || this.order_stage_details.code == 'QUOTE_SELECTIONS' || this.order_stage_details.code == 'ORDER_REJECTED') &&
                    this.permissions.modify_order) {
                    return true;
                }
                if ((this.order_stage_details.code == 'ORDER_REQUESTED' || this.order_stage_details.code == 'ORDER') &&
                    this.permissions.modify_order_requested) {
                    return true;
                }
                if (this.order_stage_details.code == 'ORDER_FINALIZED' && this.permissions.modify_order_finalized) {
                    return true;
                }
                return false;
            }

            validCustomer() {
                return this.type !== null;
            }

            validModel() {
                return _.isInteger(this.model);
            }

            validSeries() {
                return _.isInteger(this.series);
            }

            validModelSeries() {
                return this.validModel() && this.validSeries();
            }

            validWeightSize() {
                const valid = this.weight_estimate_disclaimer === true;
                return valid;
            }

            updateAddress(target, data) {
                target.name = _.get(data, 'name');
                target.street = _.get(data, 'address');
                target.suburb = _.get(data, 'suburb.name');
                target.post_code = _.get(data, 'suburb.post_code.number');
                target.state = _.get(data, 'suburb.post_code.state.id');
            }

            // full_update will default to true on all cases except when the action performed is to inherit a set of SKU details from another existing order
            // ie. when this function is called via performing the "clone" action - in which case, anything related to order status itself (not caravan) eg. order id, dealership etc
            // will not be changed and replaced - in addition to this, any Show related info from the "base" will not be passed to "clone" as well.
            updateOrder(data, full_update=true) {
                // console.log('data order type ' + data.order_type);
                // console.log(' Update Order ' + this.delivery_date + ' ' + data.delivery_date);
                // When adding a new field here, also add it in the corresponding 'reset' function
                this.model = data.model;
                this.series = data.series;
                this.custom_series_name = data.custom_series_name;
                this.custom_series_code = data.custom_series_code;
                this.series_description = data.series_description;
                this.series_code        = data.series_code;
                this.production_month   = data.production_month;
                this.production_start_date = data.production_start_date;
                this.modelSelection = data.model;
                this.seriesSelection = data.series;
                // Added to Test the delivery date Standing
                // this.delivery_date = data.delivery_date ? new Date(Date.parse(data.delivery_date)) : '';

                this.chassis = data.chassis;
                this.appretail_opportunity_no = data.appretail_opportunity_no;

                this.order_stage_details = data.order_stage_details;
                this.permissions = data.permissions;
                this.weight_estimate_disclaimer = data.weight_estimate_disclaimer_checked;
                this.custom_tare_weight = data.custom_tare_weight_kg;
                this.custom_ball_weight = data.custom_ball_weight_kg;
                this.price_adjustments.cost = parseFloat(data.price_adjustment_cost);
                this.price_adjustments.wholesale = parseFloat(data.price_adjustment_wholesale);
                this.price_adjustments.wholesale_comment = data.price_adjustment_wholesale_comment;
                this.price_adjustments.retail = parseFloat(data.price_adjustment_retail);
                this.dealer_load = parseFloat(data.dealer_load);
                this.trade_in_write_back = parseFloat(data.trade_in_write_back);
                this.trade_in_comment = data.trade_in_comment;

                this.after_sales.wholesale = parseFloat(data.after_sales_wholesale);
                this.after_sales.retail = parseFloat(data.after_sales_retail);
                this.after_sales.description = data.after_sales_description;

                this.price_comment = data.price_comment;

                this.orderconditions = data.orderconditions;
                this.aftermarketnote = data.aftermarketnote;
                this.is_expired = data.is_expired;
                this.base_order = data.id;
                this.has_missing_selections = data.has_missing_selections;
                this.items = data.items;
                this.price_changed = false;
                this.customer_plans_approved = data.customer_plans_approved;
                this.special_features_approved = data.special_features_approved;

                this.salesforce_sync_error = data.salesforce_sync_error;

                if (full_update) {
                    // console.log('full Updated ' + this.delivery_date + ' : ' + data.delivery_date + ' : ' + new Date(Date.parse(data.delivery_date)));
                    this.id = data.id;
                    this.customer = data.customer;
                    this.show_id = data.show;
                    this.show_special_id = data.show_special_id;
                    this.delivery_date = data.delivery_date ? new Date(Date.parse(data.delivery_date)) : '';
                    this.special_features = data.special_features;
                    this.special_features_changed = false;
                    this.is_order_converted = data.is_order_converted;
                    this.order_converted = data.order_converted;
                    this.last_server_error_message = data.last_server_error_message;
                    this.order_type = data.order_type;
                    this.dealership = data.dealership;
                    this.dealer_sales_rep_name = data.dealer_sales_rep_name;
                    this.customer_manager_name = data.customer_manager_name;
                    this.dealership_name = data.dealership_name;
                    this.appretail_opportunity_no = data.appretail_opportunity_no;
                }
            }

            // This function is created so that whenever an existing order is selected for 
            // Continue with this series the display totals should not show the wholesale and retail price adjustments etc.  
            updateOrder_duplicate(data, full_update=true) {

                // When adding a new field here, also add it in the corresponding 'reset' function
                this.model = data.model;
                this.series = data.series;
                this.custom_series_name = data.custom_series_name;
                this.custom_series_code = data.custom_series_code;
                this.series_description = data.series_description;
                this.series_code        = data.series_code;
                this.production_month   = data.production_month;
                this.production_start_date = data.production_start_date;
                this.modelSelection = data.model;
                this.seriesSelection = data.series;
                // Added to Test the delivery date Standing
                // this.delivery_date = data.delivery_date ? new Date(Date.parse(data.delivery_date)) : '';

                this.chassis = data.chassis;
                this.appretail_opportunity_no=data.appretail_opportunity_no;

                this.order_stage_details = data.order_stage_details;
                this.permissions = data.permissions;
                this.weight_estimate_disclaimer = data.weight_estimate_disclaimer_checked;
                this.custom_tare_weight = data.custom_tare_weight_kg;
                this.custom_ball_weight = data.custom_ball_weight_kg;
                // this.price_adjustments.cost = parseFloat(data.price_adjustment_cost);
                // this.price_adjustments.wholesale = parseFloat(data.price_adjustment_wholesale);
                // this.price_adjustments.wholesale_comment = data.price_adjustment_wholesale_comment;
                // this.price_adjustments.retail = parseFloat(data.price_adjustment_retail);
                // this.dealer_load = parseFloat(data.dealer_load);
                // this.trade_in_write_back = parseFloat(data.trade_in_write_back);
                // this.trade_in_comment = data.trade_in_comment;

                // this.after_sales.wholesale = parseFloat(data.after_sales_wholesale);
                // this.after_sales.retail = parseFloat(data.after_sales_retail);
                // this.after_sales.description = data.after_sales_description;

                this.price_comment = data.price_comment;

                this.orderconditions = data.orderconditions;
                this.aftermarketnote = data.aftermarketnote;
                this.is_expired = data.is_expired;
                this.base_order = data.id;
                this.has_missing_selections = data.has_missing_selections;
                this.items = data.items;
                this.price_changed = false;
                this.customer_plans_approved = data.customer_plans_approved;
                this.special_features_approved = data.special_features_approved;

                this.salesforce_sync_error = data.salesforce_sync_error;

                if (full_update) {
                    this.id = data.id;
                    this.customer = data.customer;
                    this.show_id = data.show;
                    this.show_special_id = data.show_special_id;
                    this.delivery_date = data.delivery_date ? new Date(Date.parse(data.delivery_date)) : '';
                    this.special_features = data.special_features;
                    this.special_features_changed = false;
                    this.is_order_converted = data.is_order_converted;
                    this.order_converted = data.order_converted;
                    this.last_server_error_message = data.last_server_error_message;
                    this.order_type = data.order_type;
                    this.dealership = data.dealership;
                    this.dealer_sales_rep_name = data.dealer_sales_rep_name;
                    this.customer_manager_name = data.customer_manager_name;
                    this.dealership_name = data.dealership_name;
                }
            }

            loadOrderDetails(id) {
                // Load the details of another order but do not override:
                // - the id
                // - the customer information
                // - the special features

                return ApiService.post('orders/retrieve-order',
                    {order_id: id})
                    .then(r => {
                        this.updateOrder(r.data, false);
                    });
            }

            loadOrderDetails_duplicate(id) {
                // Load the details of another order but do not override:
                // - the id
                // - the customer information
                // - the special features

                return ApiService.post('orders/retrieve-order',
                    {order_id: id})
                    .then(r => {
                        this.updateOrder_duplicate(r.data,false);
                    });
            }

            retrieveOrder(id) {
                const success = r => {
                    this.updateOrder(r.data);
                };
                const failure = (err) => {
                    console.log("There was an error retrieving this order");
                    return $q.reject(err);
                };
                return ApiService.post('orders/retrieve-order', {order_id: id}).then(success, failure);
            }

            saveOrder() {
                // console.log('Entered Save Order !! ');
                const success = r => {
                    // console.log(r.data);
                    this.updateOrder(r.data);
                    return $q.resolve(r);
                };
                const failure = (err) => {
                    console.log("There was an error saving this order");
                    return $q.reject(err);
                };

                let features_files = {};
                let newDocumentCount = 1;
                this.special_features.forEach(function(feature) {
                     if (feature.new_document) {
                        feature.file_id = newDocumentCount++;
                        features_files[feature.file_id] = feature.new_document;
                    }
                });
                // console.log('Before Calling POST ' +  data.order_id);    
                return Upload.upload({
                    method: 'POST',
                    url: '/api/orders/save-order',
                    data: {order: this},
                    file: features_files,
                }).then(success, failure);
            }

            saveNewOrderForCustomer() {
                const dealership = this.dealership;
                this.resetOrderExceptCustomer();
                this.dealership = dealership;
                this.order_type = 'Customer';
                return this.saveOrder();
            }

            requestOrder() {
                const success = r => {
                    this.updateOrder(r.data);
                };
                const failure = (err) => {
                    return $q.reject(err);
                };
                return ApiService.post('orders/request-order', {order: this}).then(success, failure);
            }

            rejectOrder() {
                const success = r => {
                    this.updateOrder(r.data);
                };
                const failure = (err) => {
                    return $q.reject(err);
                };
                return ApiService.post('orders/reject-order', {order: this}).then(success, failure);
            }

            placeOrder() {
                const success = r => {
                    this.updateOrder(r.data);
                };
                const failure = (err) => {
                    return $q.reject(err);
                };
                return ApiService.post('orders/place-order', {order: this}).then(success, failure);
            }

            cancelOrder(cancelReason) {
                const success = r => {
                    this.updateOrder(r.data);
                };
                const failure = (err) => {
                    return $q.reject(err);
                };
                return ApiService.post('orders/cancel-order', {order: this, cancel_reason: cancelReason}).then(success, failure);
            }

            finalizeOrder() {
                const success = r => {
                    this.updateOrder(r.data);
                };
                const failure = (err) => {
                    return $q.reject(err);
                };
                return ApiService.post('orders/finalize-order', {order: this}).then(success, failure);
            }
        }

        return new Order();
    });

};
