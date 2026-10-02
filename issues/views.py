from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
import json
import math
from django.contrib.gis.geos import Point
from django.utils import timezone
from .models import Issue, Vote, Municipio, Report


def issue_list(request):
    issues = Issue.objects.all().select_related('municipio', 'created_by')

    municipio_id = request.GET.get('municipio')
    if municipio_id and municipio_id.isdigit():
        issues = issues.filter(municipio_id=municipio_id)

    municipios = Municipio.objects.all().order_by('name')
    
    map_points = []
    for issue in issues:
        if not (math.isfinite(issue.location.x) and math.isfinite(issue.location.y)):
            continue  # um ponto inválido no banco não pode derrubar o mapa inteiro
        map_points.append({
            'lat': issue.location.y,
            'lng': issue.location.x,
            'title': issue.title,
            'url': f"/issue/{issue.pk}/"
        })

    return render(request, 'issues/issue_list.html', {
        'issues': issues,
        'municipios': municipios,
        'municipio_selecionado': municipio_id,
        'map_points': map_points,
        'map_points_json': json.dumps(map_points)
    })


def issue_detail(request, pk):
    issue = get_object_or_404(Issue, pk=pk)
    vote_count = Vote.objects.filter(issue=issue, is_active=True).count()

    user_vote = None
    if request.user.is_authenticated:
        user_vote = Vote.objects.filter(issue=issue, user=request.user).first()

    return render(request, 'issues/issue_detail.html', {
        'issue': issue,
        'vote_count': vote_count,
        'user_vote': user_vote,
    })


@login_required
def issue_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        municipio_id = request.POST.get('municipio')
        lat = request.POST.get('lat')
        lng = request.POST.get('lng')

        def form_error(msg):
            # re-renderiza com o que o usuário digitou, pra não perder o texto
            messages.error(request, msg)
            return render(request, 'issues/issue_form.html', {
                'municipios': Municipio.objects.all().order_by('name'),
                'form_data': request.POST,
            })

        if not all([title, description, municipio_id, lat, lng]):
            return form_error('Preencha todos os campos e marque o local no mapa.')

        max_title = Issue._meta.get_field('title').max_length
        if len(title) > max_title:
            return form_error(f'O título pode ter no máximo {max_title} caracteres.')

        municipio = Municipio.objects.filter(pk=municipio_id).first() if municipio_id.isdigit() else None
        if municipio is None:
            return form_error('Município inválido.')

        try:
            lat, lng = float(lat), float(lng)
        except ValueError:
            lat = lng = math.nan
        if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
            return form_error('Localização inválida. Marque o local no mapa.')

        location = Point(lng, lat, srid=4326)
        if not municipio.boundary.contains(location):
            correto = Municipio.objects.filter(boundary__contains=location).first()
            dica = f' O ponto marcado fica em {correto.name}.' if correto else ''
            return form_error(f'O local marcado não fica em {municipio.name}.{dica}')

        issue = Issue.objects.create(
            title=title,
            description=description,
            location=location,
            municipio=municipio,
            created_by=request.user,
        )
        messages.success(request, 'Issue criado com sucesso.')
        return redirect('issues:issue_detail', pk=issue.pk)

    municipios = Municipio.objects.all().order_by('name')
    return render(request, 'issues/issue_form.html', {'municipios': municipios})


@login_required
@require_POST
def vote_toggle(request, pk):
    issue = get_object_or_404(Issue, pk=pk)

    existing_vote = Vote.objects.filter(issue=issue, user=request.user).first()

    if existing_vote is None:
        Vote.objects.create(issue=issue, user=request.user)
        messages.success(request, 'Voto registrado.')
    elif existing_vote.is_active:
        # revogação: nunca edita o voto original, já que é append-only —
        # apenas marca is_active=False, o que a trigger permite
        existing_vote.is_active = False
        existing_vote.revoked_at = timezone.now()
        existing_vote.save()
        messages.info(request, 'Voto revogado.')
    else:
        messages.warning(request, 'Este voto já foi revogado anteriormente e não pode ser reativado.')

    return redirect('issues:issue_detail', pk=pk)

def user_is_moderator(user):
    return user.is_superuser or user.groups.filter(name='Moderadores').exists()


@login_required
@require_POST
def report_issue(request, pk):
    issue = get_object_or_404(Issue, pk=pk)
    reason = request.POST.get('reason', '')
    Report.objects.get_or_create(
        issue=issue, reported_by=request.user,
        defaults={'reason': reason}
    )
    messages.success(request, 'Denúncia registrada. Um moderador vai revisar.')
    return redirect('issues:issue_detail', pk=pk)


@login_required
def moderation_queue(request):
    if not user_is_moderator(request.user):
        messages.error(request, 'Acesso restrito a moderadores.')
        return redirect('issues:issue_list')

    reports = Report.objects.filter(resolved=False).select_related('issue', 'reported_by')
    return render(request, 'issues/moderation_queue.html', {'reports': reports})


@login_required
@require_POST
def moderate_hide(request, report_id):
    if not user_is_moderator(request.user):
        return redirect('issues:issue_list')

    report = get_object_or_404(Report, pk=report_id)
    report.issue.soft_delete()
    # ocultar o issue resolve todas as denúncias pendentes dele, não só esta
    Report.objects.filter(issue=report.issue, resolved=False).update(
        resolved=True, resolved_by=request.user, resolved_at=timezone.now()
    )
    messages.success(request, 'Issue ocultado.')
    return redirect('issues:moderation_queue')


@login_required
@require_POST
def moderate_dismiss(request, report_id):
    if not user_is_moderator(request.user):
        return redirect('issues:issue_list')

    report = get_object_or_404(Report, pk=report_id)
    report.resolved = True
    report.resolved_by = request.user
    report.resolved_at = timezone.now()
    report.save()
    messages.info(request, 'Denúncia descartada, issue mantido.')
    return redirect('issues:moderation_queue')
