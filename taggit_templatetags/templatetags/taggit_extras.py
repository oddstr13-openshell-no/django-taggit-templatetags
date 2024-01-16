from django import template
from django.db import models
from django.db.models import Count
from django.core.exceptions import FieldError
from django.contrib.contenttypes.models import ContentType

from templatetag_sugar.register import tag
from templatetag_sugar.parser import Name, Variable, Constant, Optional, Model

from taggit import VERSION as TAGGIT_VERSION
from taggit.managers import TaggableManager
from taggit.models import TaggedItem, Tag
from taggit_templatetags import settings

T_MAX = getattr(settings, 'TAGCLOUD_MAX', 6.0)
T_MIN = getattr(settings, 'TAGCLOUD_MIN', 1.0)

register = template.Library()

def _count(a_list):
    result = {}
    for elem in a_list:
        if elem in result:
            result[elem] += 1
        else:
            result[elem] = 1
    return result


def get_queryset(forvar=None):
    if None == forvar:
        # get all tags
        queryset = Tag.objects.all()
        occurrences = {}
    elif isinstance(forvar, str):
        # extract app label and model name
        beginning, applabel, model = None, None, None
        try:
            beginning, applabel, model = forvar.rsplit('.', 2)
        except ValueError:
            try:
                applabel, model = forvar.rsplit('.', 1)
            except ValueError:
                applabel = forvar
        
        # filter tagged items        
        if applabel:
            queryset = TaggedItem.objects.filter(content_type__app_label=applabel.lower())
        if model:
            queryset = queryset.filter(content_type__model=model.lower())
            
        # get tags
        # this is interesting: if we don't make tag_ids as a list, even if
        # empty it will get all the tags from Tag.objects.filter(id__in=tag_ids)
        tag_ids = list(queryset.values_list('tag_id', flat=True))
        queryset = Tag.objects.filter(id__in=tag_ids)
        occurrences = _count(tag_ids)
    else:
        if len(forvar) == 0:
            queryset = TaggedItem.objects.none()
        else:
            ctype = ContentType.objects.get_for_model(forvar[0])
            queryset = TaggedItem.objects.filter(content_type=ctype)\
                        .filter(object_id__in=[x.pk for x in forvar])

        # get tags
        tag_ids = list(queryset.values_list('tag_id', flat=True))
        queryset = Tag.objects.filter(id__in=tag_ids)
        occurrences = _count(tag_ids)

    # Retain compatibility with older versions of Django taggit
    # a version check (for example taggit.VERSION <= (0,8,0)) does NOT
    # work because of the version (0,8,0) of the current dev version of django-taggit
    try:
        return queryset.annotate(num_times=Count('taggeditem_items')), occurrences
    except FieldError:
        return queryset.annotate(num_times=Count('taggit_taggeditem_items')), occurrences

def get_weight_fun(t_min, t_max, f_min, f_max):
    def weight_fun(f_i, t_min=t_min, t_max=t_max, f_min=f_min, f_max=f_max):
        # Prevent a division by zero here, found to occur under some
        # pathological but nevertheless actually occurring circumstances.
        if f_max == f_min:
            mult_fac = 1.0
        else:
            mult_fac = float(t_max-t_min)/float(f_max-f_min)
            
        return t_max - (f_max-f_i)*mult_fac
    return weight_fun

@tag(register, [Constant('as'), Name(), Optional([Constant('for'), Variable()])])
def get_taglist(context, asvar, forvar=None):
    queryset, _ = get_queryset(forvar)
    queryset = queryset.order_by('-num_times')        
    context[asvar] = queryset
    return ''

@tag(register, [Constant('as'), Name(), Optional([Constant('for'), Variable()])])
def get_tagcloud(context, asvar, forvar=None):
    queryset, occurrences = get_queryset(forvar)

    num_times = occurrences.values() if len(occurrences) \
        else queryset.values_list('num_times', flat=True)
    if(len(num_times) == 0):
        context[asvar] = queryset
        return ''
    weight_fun = get_weight_fun(T_MIN, T_MAX, min(num_times), max(num_times))
    queryset = queryset.order_by('name')
    for i, tag in enumerate(queryset):
        tag.weight = weight_fun(occurrences.get(tag.pk, tag.num_times))
    context[asvar] = queryset
    return ''
    
def include_tagcloud(forvar=None):
    return {'forvar': forvar}

def include_taglist(forvar=None):
    return {'forvar': forvar}
  
register.inclusion_tag('taggit_templatetags/taglist_include.html')(include_taglist)
register.inclusion_tag('taggit_templatetags/tagcloud_include.html')(include_tagcloud)
