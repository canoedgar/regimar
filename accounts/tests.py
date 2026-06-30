from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class HomeDashboardTests(TestCase):
    def test_home_dashboard_renders_for_user_with_sales_permissions(self):
        user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="secret",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"), follow=True)

        self.assertEqual(response.status_code, 200)
