from django.urls import path
from . import views

app_name = 'issues'

urlpatterns = [
    path('', views.issue_list, name='issue_list'),
    path('issue/<int:pk>/', views.issue_detail, name='issue_detail'),
    path('issue/novo/', views.issue_create, name='issue_create'),
    path('issue/<int:pk>/votar/', views.vote_toggle, name='vote_toggle'),
    path('issue/<int:pk>/denunciar/', views.report_issue, name='report_issue'),
    path('moderacao/', views.moderation_queue, name='moderation_queue'),
    path('moderacao/<int:report_id>/ocultar/', views.moderate_hide, name='moderate_hide'),
    path('moderacao/<int:report_id>/descartar/', views.moderate_dismiss, name='moderate_dismiss'),
    path('issue/<int:pk>/denunciar/', views.report_issue, name='report_issue'),
    path('moderacao/', views.moderation_queue, name='moderation_queue'),
    path('moderacao/<int:report_id>/ocultar/', views.moderate_hide, name='moderate_hide'),
    path('moderacao/<int:report_id>/descartar/', views.moderate_dismiss, name='moderate_dismiss'),
]
