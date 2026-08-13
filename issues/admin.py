from django.contrib import admin

from issues.models import Municipio, Issue,Vote,Report


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    list_display = ('name', 'codigo_ibge')
    search_fields = ('name', 'codigo_ibge')


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('title', 'municipio', 'created_by', 'created_at', 'is_deleted')
    list_filter = ('municipio', 'is_deleted')
    search_fields = ('title', 'description')
    readonly_fields = ('record_hash', 'previous_hash', 'created_at')  # imutável, então nem faz sentido editar


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('issue', 'user', 'created_at', 'is_active')
    list_filter = ('is_active',)
    readonly_fields = ('record_hash', 'previous_hash', 'created_at')  # append-only, admin também não deve poder editar


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('issue', 'reported_by', 'reason', 'resolved', 'created_at')
    list_filter = ('resolved',)
# Register your models here.
