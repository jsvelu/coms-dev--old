import _ from 'lodash';

export default app => {

    app.factory('OrderApiService', (ApiService) => {

        class OrderApi {

            getFeatures(seriesId, orderId,delivery_date) {

                return ApiService.getData('orders/series-items', {
                    series_id: seriesId,
                    order_id: orderId,
                    required_date:delivery_date,

                });
            }

        }

        return new OrderApi();
    });
};