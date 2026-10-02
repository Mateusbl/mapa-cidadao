def moderation(request):
    from .views import user_is_moderator
    user = request.user
    return {'is_moderator': user.is_authenticated and user_is_moderator(user)}
