import json

from django.core.management.base import BaseCommand

from apps.customers.services.rusprofile import RusProfileParser


class Command(BaseCommand):
    help = "Тест парсера RusProfile по ИНН"

    def add_arguments(self, parser):
        parser.add_argument("--inn", required=True, help="ИНН компании")

    def handle(self, *args, **options):
        inn = options["inn"]
        self.stdout.write(f"Парсим RusProfile для ИНН {inn}...")

        parser = RusProfileParser()
        result = parser.get_company_info(inn)

        if not result:
            self.stderr.write(self.style.ERROR("Не удалось получить данные"))
            return

        self.stdout.write(self.style.SUCCESS(f"\nРезультат для ИНН {inn}:"))
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        self.stdout.write(f"\n--- Сводка ---")
        self.stdout.write(f"Название:     {result.get('name', '—')}")
        self.stdout.write(f"Статус:       {result.get('status', '—')}")
        self.stdout.write(f"Руководитель: {result.get('director_name', '—')}")
        self.stdout.write(f"Регион:       {result.get('region', '—')}")
        self.stdout.write(f"Дата рег.:    {result.get('founded_date', '—')}")
        self.stdout.write(f"Выручка:      {result.get('revenue_rub', '—')} ({result.get('revenue_year', '—')})")
        self.stdout.write(f"Прибыль:      {result.get('profit_rub', '—')}")
        self.stdout.write(f"Сотрудники:   {result.get('employees_count', '—')}")
        self.stdout.write(f"Лицензии:     {result.get('licenses_count', '—')}")
        self.stdout.write(f"Лиц. текст:   {result.get('licenses_summary', '—')}")
        self.stdout.write(f"Закупки (зак): {result.get('purchases_customer_count', '—')}")
        self.stdout.write(f"Закупки сум.:  {result.get('purchases_customer_amount', '—')}")
        self.stdout.write(f"Арбитраж:     {result.get('arbitration_count', '—')}")
        self.stdout.write(f"ФССП:         {result.get('fssp_count', '—')}")
        self.stdout.write(f"RusProfile ID: {result.get('rusprofile_id', '—')}")
