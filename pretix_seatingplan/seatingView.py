from asyncio import events
import io
# from msilib.schema import Error
import sys
from multiprocessing import Event
from re import template
from sre_parse import CATEGORIES
from typing import Mapping
from unicodedata import category

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Sum
from .seatingForm import SeatingForm
from django.http import (
    Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect,
    JsonResponse,HttpRequest
)
from pretix.control.permissions import EventPermissionRequiredMixin

from django.shortcuts import redirect, render
from django.urls import resolve, reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic.detail import DetailView
from pretix.multidomain.urlreverse import eventreverse


import json
from base64 import b64encode
from django.views.generic import (
    FormView,ListView
)
import requests
import pprint
from pretix.base.models import ( SeatingPlan , SeatCategoryMapping,Item, Seat,SubEvent)

from django.contrib.auth.models import User
from rest_framework import generics
from rest_framework import viewsets
from rest_framework import serializers
from django.shortcuts import redirect
from pretix.api.views.organizer import  SeatingPlanViewSet,TeamAPITokenViewSet,TeamViewSet,TeamMemberViewSet
from pretix.api.views.event import EventViewSet
from pretix.api.serializers.organizer import (
    SeatingPlanSerializer
)
from pretix.base.models import (
    SeatingPlan,Seat
)
from pretix.base.services.seating import (
    generate_seats
)

from pretix.api.serializers.event import (
    EventSerializer,

)


def DisplaySeriesTable(request,**kwargs):
    if not request.event.has_subevents:
        return redirect(reverse('plugins:pretix_seatingplan:event.seating.display',kwargs={
            'event':request.event.slug,
            'organizer':request.organizer.slug
        }))

    subevents = request.event.subevents.all()
    return render(request,'pretix_seatingplan/subevents.html',{'subevents':subevents})



# displaying the seating plan and setting the seatcategory mapping
def DisplaySeating(request,**kwargs):
    if ('subevent' in request.GET) and request.event.has_subevents: # TODO understand subevents
            subevent = request.GET['subevent']
            subevent_ob = SubEvent.objects.filter(id=subevent)[0]
    else :
        subevent_ob = None

    # Why is there a POST method in a view called Display Something, would maybe need to refactor this out
    # Because there is a form on the display page that updates the categories somehow.
    if (request.method == 'POST'):
        if subevent_ob is not None :
            maps = SeatCategoryMapping.objects.filter(event=request.event)
        else :
            maps = SeatCategoryMapping.objects.filter(event=request.event, subevent=subevent_ob) # This is weird, because we only pass the subevent_ob parameter when is is None ?

        if maps is not None:
            maps.delete() # Why do we delete maps here if we just created it ? Maybe its a delete in the database -> Yes it is, it cleans the previous record I think
            
        items_cats = list(request.POST.keys())[1:] 

        for item_cat in items_cats:
            item_name, cat = item_cat.split('_____') # That is not very clean if it is a design choice and not a constraint somehow
            iteml = Item.objects.filter(event_id = request.event.id)
            itemn = [ itemll for itemll in iteml if str(itemll.name) == item_name ][0]

            if ('subevent' in request.GET) and request.event.has_subevents :
                queryset = SeatCategoryMapping.objects.create(event=request.event, subevent=subevent_ob, layout_category=cat, product=itemn)
            else :
                queryset = SeatCategoryMapping.objects.create(event=request.event, layout_category=cat, product=itemn)
            
            queryset.save()

    if ('subevent' in request.GET) and request.event.has_subevents: # Same check as above, why do it twice
        categories = SeatingPlan.objects.filter(organizer=request.event.organizer, subevents=subevent)[0].layout_data['categories']
    else :
        seating_plans  = SeatingPlan.objects.filter(organizer=request.event.organizer, events=request.event)

        if len(seating_plans) > 0:
            categories = seating_plans[0].layout_data['categories']  # Why would we always take the first one ? Could be nice to be able to select one
        else:
            return  redirect(reverse('plugins:pretix_seatingplan:event.seating.subevents', kwargs={
            'event': request.event.slug,
            'organizer': request.event.organizer.slug
        }))

    items = Item.objects.filter(event_id=request.event.id) # What do we have in here ?

    categories_dict = { cat['name'] : [(item, 'off') for item in items] for cat in categories }
    
    if ('subevent' in request.GET) and request.event.has_subevents: # And a third time
        category_maps = SeatCategoryMapping.objects.filter(event_id=request.event.id, subevent_id=subevent_ob.id)
    else :
        category_maps = SeatCategoryMapping.objects.filter(event_id=request.event.id)

    # setting the 'category item map' in the dict that we will render only if we find it in the intermediate table
    for cat_map in category_maps:
        cat_dict = categories_dict[cat_map.layout_category]
        if cat_dict is not None:
            for i,item_tup in enumerate(cat_dict) :
                if cat_map.product.id == item_tup[0].id:
                    categories_dict[cat_map.layout_category][i] = (item_tup[0],'on')
    
    url_reverse = eventreverse(request.event,'plugins:pretix_seatingplan:event.seating.displaydata')
    if subevent_ob is not None:
        url_reverse = eventreverse(request.event,'plugins:pretix_seatingplan:event.seating.displaydata',kwargs={
            'subevent':subevent_ob.id
        })
    return render(request,'pretix_seatingplan/display.html',{'categories':categories_dict,'url_data':url_reverse})    

class Mapping :
    def get(self,x):
        return None 

# used to save a specfic seating plan 
class UploadSeating(EventPermissionRequiredMixin, FormView):
    template_name = 'pretix_seatingplan/index.html'
    form_class = SeatingForm
    permission = 'can_change_event_settings'

    def get_success_url(self, **kwargs):
        return reverse('plugins:pretix_seatingplan:event.seating.display', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })
        
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['has_subevents'] = self.request.event.has_subevents
        ctx['subevents'] = self.request.event.subevents.all()
        return ctx
        
    def form_valid(self,form) -> str :
        file = self.request.FILES['file']
        body_data = json.loads(file.read().decode().replace("'",'"'))
        
        try:
            ser = SeatingPlanSerializer(data ={'name': file.name[:file.name.index('.')]+' new','layout': body_data})

            if ser.is_valid():
                seat_plan = ser.save(organizer=self.request.organizer)
                self.request.event.seating_plan = seat_plan
                self.request.event.save()
                subevent = None
                if 'subevent' in self.request.GET:
                    subevent = SubEvent.objects.get(id=self.request.GET['subevent'])    
                    subevent.seating_plan = seat_plan
                    subevent.save()

                gen_seats_result = generate_seats(self.request.event,subevent,seat_plan, Mapping())

                print(gen_seats_result)

                messages.success(self.request, _('A seating plan has been added to '+self.request.event.slug+' with success'))
            else:
                print("Not valid oups")
                messages.error(self.request,_('ERROR'))
        except Exception as e:
            print("Big error", e)
            messages.error(self.request,_('ERROR'))
        if subevent:
            return redirect(self.get_success_url()+'?subevent='+self.request.GET['subevent'])
        return redirect(self.get_success_url())
        
    

def test (request,**kwargs):
    # This doesn't show anything, are the seats correctly created ?
    # I think not because nothing shows up in the database in pretixbase_seat
    print(Seat.objects.all())
    return HttpResponse(Seat.objects.all())
        