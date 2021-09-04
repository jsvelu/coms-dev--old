import _ from 'lodash';

export default app => {

    app.factory('SchedulePlannerApiService', (ApiService) => {


        class SchedulePlannerApi {

            getInitialData() {
                return ApiService.getData('schedule/planner/initial');
            }

            saveData(data,month_picker_data) {
                let d = month_picker_data;
                let currMonth = d.getMonth() + 1;
                let currYear = d.getFullYear();
                let desired_format = currYear + "/" + currMonth + "/01";

                return ApiService.postData('schedule/planner/save', {
                    'data': data,
                    'month_picker_data': desired_format,
                });
            }
            updateMonth(month_picker_data) {
                let d = month_picker_data;
                let currMonth = d.getMonth() + 1;
                let currYear = d.getFullYear();
                let desired_format = currYear + "/" + currMonth + "/01";
                return ApiService.postData('schedule/planner/update_month', {
                    'month_picker_data': desired_format,
                });
            }
        }
        return new SchedulePlannerApi();
    });
};