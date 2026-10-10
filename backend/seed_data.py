from django.contrib.auth import get_user_model
from platform_api.models import ForexPairConfig

User = get_user_model()

# Create admin if missing
email = 'admin@tradeflow.local'
pw = 'change-me'
if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(email=email, password=pw)
    print(f"Created admin: {email}")
else:
    u = User.objects.get(email=email)
    print(f"Admin exists: {email} (id={u.id})")

# Seed forex pairs
pairs = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD",
    "USD/CAD", "NZD/USD", "EUR/GBP", "EUR/JPY", "GBP/JPY",
]
for sym in pairs:
    obj, created = ForexPairConfig.objects.get_or_create(
        symbol=sym,
        defaults={"is_watched": True, "default_qty": 1000.0}
    )
    if created:
        print(f"Seeded pair: {sym}")

print(f"Total forex pairs in DB: {ForexPairConfig.objects.count()}")
print("SEED COMPLETE")
