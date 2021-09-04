

import authtools.views

from django.core.exceptions import ObjectDoesNotExist
from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.sessions.models import Session
from django.contrib.auth.models import User, Group
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate
from django.contrib.auth import login  
# from django.contrib.auth import login as auth_login

from django.http import Http404, HttpResponseRedirect
from django.http import JsonResponse

from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import TemplateView

from caravans.models import Series
from orders.models import Order
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

class LoginView(authtools.views.LoginView):
    """
    Login action
    """
    allow_authenticated = False # they have to log out before they can log in again
    #template_name = 'registration/login.html'
    template_name = 'admin/login.html'

    def get_success_url(self):
        # user = self.request.user
        # Redirect to different places after login?
        # Generate the tokens for the users

        my_token= Token.objects.get_or_create(user=self.request.user)[0]

        return super(LoginView, self).get_success_url()


class LogoutView(authtools.views.LogoutView):
    """
    Logout action
    """
    template_name = 'registration/logged_out.html'


class MaintenanceView(TemplateView):
    template_name = 'newage/maintenance.html'

class TokenLogin(TemplateView):
    template_name = 'newage/maintenance.html'
    # permission_classes = [IsAuthenticated]
    # authentication_classes = [authentication.TokenAuthentication]
    def post(self,request, *args, **kwargs):

        session_key = self.request.POST.get('session_key')

        order_id = self.request.POST.get('order_id')

        session = Session.objects.get(session_key=session_key)
        session_data = session.get_decoded()
        #print (session_data)
        uid = session_data['_auth_user_id']
        #print(uid)
        User = get_user_model()

        user = User.objects.get(id=uid)

        #print('User Id',uid,'Name',user.name)
        # TokenLogin.uname=self.request.user.name
        # print('Name : ',TokenLogin.uname)

        authenticate(user)
        # login(request, user,backend='django.contrib.auth.backends.ModelBackend')

        session_key=self.request.session.session_key
        #print('session',session_key)

        url_to_go = '/newage/orders/#/' + str(self.request.POST.get('order_id')) + '/status'
        
        return HttpResponseRedirect(url_to_go)


    def get(self,request, *args, **kwargs):
        # print('GET requested')

        session_key = self.request.GET.get('session_key')
        # print (session_key)

        view_type= request.GET.get('view_type')

        url_to_go = None
        
        if(view_type=='order_status'):
            order_id = self.request.GET.get('order_id')
            if order_id is not None:

                try:
                    order = Order.objects.get(id=order_id)
                except ObjectDoesNotExist:
                    return JsonResponse({" Erro " : " Invalid Order Id  !! Please Enter Valid Quote or Id  " })
                
                # print(order_id)
                url_to_go = '/newage/orders/#/' + str(self.request.GET.get('order_id')) + '/status'

        if(view_type=='series_specs'):
            series_id = self.request.GET.get('series_id')

            try:
                series=Series.objects.get(id=series_id)
            except ObjectDoesNotExist:
                return JsonResponse({" Erro " : " Invalid Series Id  !! Please Enter A Valid Series Id to View Specs" })

            # print('Series id ' + series_id)
            url_to_go = '/caravans/browse_models/' + str(series_id) + '/specs'


        if(view_type=='series_options'):
            series_id = self.request.GET.get('series_id')

            try:
                series=Series.objects.get(id=series_id)
            except ObjectDoesNotExist:
                return JsonResponse({" Erro " : " Invalid Series Id  !! Please Enter A Valid Series Id to View Options and Upgrades" })

            url_to_go = '/caravans/browse_models/' + str(series_id) + '/option_upgrade'

        if(view_type=='series_floor_plan'):
            series_id = self.request.GET.get('series_id')

            try:
                series=Series.objects.get(id=series_id)
            except ObjectDoesNotExist:
                return JsonResponse({" Erro " : " Invalid Series Id  !! Please Enter A Valid Series Id to View Floor Plan" })

            url_to_go = '/caravans/browse_models/' + str(series_id) + '/floor_plan'


        if(view_type=='order_specs'):
            order_id = self.request.GET.get('order_id')
            if order_id is not None:

                try:
                    order = Order.objects.get(id=order_id)
                except ObjectDoesNotExist:
                    return JsonResponse({" Erro " : " Invalid Order Id  !! Please Enter Valid Order Id  " })
                
                # print(order_id)
                url_to_go = '/orders/spec/' + str(order_id) + '/'

        if(view_type=='home'):
            url_to_go = '/home/'

        if(view_type=='password_change'):
            url_to_go = '/password_change/'

        try:
            session = Session.objects.get(session_key=session_key)
        except ObjectDoesNotExist:
            return JsonResponse({" Erro " : " Invalid Session  !! Please Login With Valid Credentials ! " })
        
        session_data = session.get_decoded()
        # print (session_data)
        uid = session_data['_auth_user_id']
        # print(uid)
        User = get_user_model()

        user = User.objects.get(id=uid)

        # print('User Id',uid,'Name',user.name)
        # TokenLogin.uname=self.request.user.name
        # print('Name : ',TokenLogin.uname)
        # authenticate(user)

        if (user.is_authenticated):
            # print('User authenticated')
            pass

        else:
            # print('User Is Not authenticated')
            return JsonResponse({" Error " : " User id not authenticated  !!" })

        login(request, user,backend='django.contrib.auth.backends.ModelBackend')

        session_key=self.request.session.session_key

        
        if url_to_go is None:
            return JsonResponse({" Error " : " view_type is not Indicated  !!" })        

        else:

            return HttpResponseRedirect(url_to_go)
        

    

@sensitive_post_parameters()
@csrf_protect
@login_required
def password_change(request,
                    template_name='registration/password_change_form.html',
                    post_change_redirect=None,
                    password_change_form=PasswordChangeForm,
                    current_app=None, extra_context=None):

    # Call the django password change method, but use our template (out of admin)

    return auth.views.password_change(request,
        template_name,
        post_change_redirect,
        password_change_form,
        current_app, extra_context)


@login_required
def password_change_done(request,
                         template_name='registration/password_change_done.html',
                         current_app=None, extra_context=None):

    # Call the django password change method, but use our template (out of admin)

    return auth.views.password_change_done(request,
        template_name,
        current_app,
        extra_context)
