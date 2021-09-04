import _ from 'lodash';

export default app => {

    app.factory('ScheduleDealerApiService', (ApiService) => {


        class ScheduleDealerApi {

            getInitialData() {
                return ApiService.getData('schedule/dealership/initial');
            }

            saveData(dealers_capacity_data,month_picker_data) {
                let d = month_picker_data;
                let currMonth = d.getMonth() + 1;
                let currYear = d.getFullYear();
                let desired_format = currYear + "/" + currMonth + "/01";
                return ApiService.postData('schedule/dealership/save', {
                    'dealers_capacity_data': dealers_capacity_data,'month_picker_data': desired_format
                });
            }
            updateMonth(month_picker_data) {
                let d = month_picker_data;
                let currMonth = d.getMonth() + 1;
                let currYear = d.getFullYear();
                let desired_format = currYear + "/" + currMonth + "/01";
                return ApiService.postData('schedule/dealership/update-month', {
                    'month_picker_data': desired_format,
                });
            }
            
            
        }

        return new ScheduleDealerApi();
    });
};

// const date_control_to_string_date = (date_control_date) => {

//     console.log(date_control_date );

//     let d = date_control_date;
//     let currDate = d.getDate();
//     let currMonth = d.getMonth()+1;
//     let currYear = d.getFullYear();
//     let desired_format= currDate + "-" + currMonth + "-" + currYear;

//     console.log(typeof currDate);
//     console.log( ' Converted Date format' + desired_format );
//     // checkValidAndUpdate(form, 'actual_production_date', desired_format);
    
//     return desired_format ;
// };
