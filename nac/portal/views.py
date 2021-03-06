import base64
import uuid

from django.contrib import messages
from django.core.files.base import ContentFile
from django.urls import reverse_lazy
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic.base import TemplateView
from django.views.generic.edit import FormView
from rest_framework.views import APIView

from portal.forms import PhotoManagerForm
from portal.models import PortalImage
from portal.models import PortalImageCollection
from production.models import Build
from production.models import Checklist
from production.models import OutcomeImage
from production.models import Step


class DisplayCollectionView(TemplateView):
    template_name = "portal/display_collection.html"

    def get_context_data(self, **kwargs):
        context = super(DisplayCollectionView, self).get_context_data(**kwargs)
        url_hash = self.kwargs.get('url_hash')

        collection = get_object_or_404(PortalImageCollection.objects, url_hash=url_hash)
        images = collection.portalimage_set.filter(is_shared=True)

        build_collection = OutcomeImage.objects.filter(outcome__build_id=collection.build.pk).filter(is_shared=True)

        context['images'] = images
        context['build_images'] = build_collection

        return context


class PhotoManagerView(FormView):
    template_name = "portal/photo_manager.html"
    form_class = PhotoManagerForm

    def get_success_url(self):
        return reverse_lazy("portal:manage_photos", kwargs={'build_id': self.kwargs['build_id']})

    def get_initial(self):
        initial = super(PhotoManagerView, self).get_initial()
        return initial

    def get_context_data(self, **kwargs):
        context = super(PhotoManagerView, self).get_context_data(**kwargs)
        build_id = self.kwargs.get('build_id')

        collection = get_object_or_404(PortalImageCollection.objects, build_id=build_id)
        miscellaneous_images = collection.portalimage_set.all()

        build_collection = OutcomeImage.objects.filter(outcome__build_id=build_id)

        qa_collection = build_collection.filter(outcome__step__checklist__section=Checklist.BUILD_SECTION_QUALITY)
        production_collection = build_collection.filter(outcome__step__checklist__section=Checklist.BUILD_SECTION_PRODUCTION)

        context['miscellaneous_images'] = miscellaneous_images
        context['qa_images'] = qa_collection
        context['production_images'] = production_collection

        context['cummulative_photo_count'] = len(miscellaneous_images) + len(qa_collection) + len(production_collection)

        context['build_id'] = build_id

        return context

    def form_valid(self, form):
        decoded_file = base64.b64decode(form.cleaned_data['hdn_pic_data'])
        extension = "png"
        content_file = ContentFile(decoded_file, name=list(self.request.FILES.values())[0].name)

        image = PortalImage()

        image.image_collection = PortalImageCollection.objects.get(build_id=self.kwargs['build_id'])
        image.image_file = content_file
        image.recorded_on = timezone.now()
        image.recorded_by = self.request.user

        image.save()

        return super(PhotoManagerView, self).form_valid(form)


class DisplayPictureView(FormView):
    template_name = "portal/image_page.html"
    form_class = PhotoManagerForm

    def get_success_url(self):
        return reverse_lazy("portal:display_picture", kwargs={'build_id': self.kwargs['build_id']})

    def get_initial(self):
        initial = super(DisplayPictureView, self).get_initial()
        return initial

    def get_context_data(self, **kwargs):
        context = super(DisplayPictureView, self).get_context_data(**kwargs)
        image_id = self.kwargs.get('image_id')
        image_type = self.kwargs.get('image_type')

        if image_type == "build":
            image = OutcomeImage.objects.get(id=image_id).image_file.url

        if image_type == "misc":
            image = PortalImage.objects.get(id=image_id).image_file.url


        context['image_url'] = image
        context['display_collection_url'] = self.request.path

        return context


class PhotoOpsView(APIView):
    permission_required = "portal.make_images_visible"

    def post(self, request, *args, **kwargs):

        operation = request.POST.get('hdn_op')

        if operation == 'update':
            self.update(request, self.kwargs.get('build_id'))

        if operation == 'delete':
            self.delete_image(request)

        return HttpResponseRedirect(request.path.replace('photo_op', 'manage_photos'))

    def update(self, request, build_id):

        def select_image_collection(images):
            for image in images:
                image.is_shared = True
                image.save()

        def unselect_image_collection(images):
            for image in images:
                image.is_shared = False
                image.save()

        collection = PortalImageCollection.objects.get(build_id=build_id)
        selected_miscellaneous_items = []
        selected_production_items = []
        selected_qa_items = []

        for key, val in list(request.POST.items()):
            if 'select_miscellaneous_image' in key:
                selected_miscellaneous_items.append(key.replace('select_miscellaneous_image', ''))
            if 'select_production_image' in key:
                selected_production_items.append(key.replace('select_production_image', ''))
            if 'select_qa_image' in key:
                selected_qa_items.append(key.replace('select_qa_image', ''))

        selected_miscellaneous_images = PortalImage.objects.filter(image_collection_id=collection.pk).filter(id__in=selected_miscellaneous_items)
        unselected_miscellaneous_images = PortalImage.objects.filter(image_collection_id=collection.pk).exclude(id__in=selected_miscellaneous_items)

        build_images = OutcomeImage.objects.filter(outcome__build_id=build_id)
        production_images = build_images.filter(outcome__step__checklist__section=Checklist.BUILD_SECTION_PRODUCTION)
        qa_images = build_images.filter(outcome__step__checklist__section=Checklist.BUILD_SECTION_QUALITY)

        selected_production_images = production_images.filter(id__in=selected_production_items)
        unselected_production_images = production_images.exclude(id__in=selected_production_items)

        selected_qa_images = qa_images.filter(id__in=selected_qa_items)
        unselected_qa_images = qa_images.exclude(id__in=selected_qa_items)

        select_image_collection(selected_miscellaneous_images)
        unselect_image_collection(unselected_miscellaneous_images)

        select_image_collection(selected_production_images)
        unselect_image_collection(unselected_production_images)

        select_image_collection(selected_qa_images)
        unselect_image_collection(unselected_qa_images)

        messages.add_message(request._request, messages.INFO, 'Your sharing preferences have been updated successfully.')

        return

    def delete_image(self, request):
        PortalImage.objects.get(pk=request.POST.get('hdn_deletable_image_id')).delete()
        return
