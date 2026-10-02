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
    # conteúdo é imutável (trigger no banco), só o soft delete pode mudar
    readonly_fields = ('title', 'description', 'location', 'municipio', 'created_by',
                       'record_hash', 'previous_hash', 'created_at')

    def get_queryset(self, request):
        # o manager padrão esconde os ocultados; o admin precisa vê-los pra poder restaurar
        return Issue.all_objects.select_related('municipio', 'created_by')

    def has_delete_permission(self, request, obj=None):
        return False  # delete físico é bloqueado pelo banco, use is_deleted


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('issue', 'user', 'created_at', 'is_active')
    list_filter = ('is_active',)
    # append-only: só a revogação (is_active/revoked_at/revoked_reason) pode mudar
    readonly_fields = ('issue', 'user', 'record_hash', 'previous_hash', 'created_at')

    def has_add_permission(self, request):
        return False  # votos entram pelo site, pra passar pelo hash chain e pelo Verifier

    def has_delete_permission(self, request, obj=None):
        return False  # bloqueado pelo trigger


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('issue', 'reported_by', 'reason', 'resolved', 'created_at')
    list_filter = ('resolved',)
# Register your models here.
