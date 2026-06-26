import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        verify_token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and verify_token == settings.WHATSAPP_VERIFY_TOKEN:
            return HttpResponse(challenge, status=200, content_type="text/plain")

        return HttpResponse("Token de verificación inválido", status=403)

    if request.method == "POST":
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}

        print("Webhook WhatsApp recibido:", payload)

        return JsonResponse({"status": "ok"}, status=200)