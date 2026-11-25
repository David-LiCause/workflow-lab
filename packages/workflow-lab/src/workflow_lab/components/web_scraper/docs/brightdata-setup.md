# Bright Data setup (fallback backend)

Pricing and steps checked against Bright Data's docs and pricing page on 2026-11-22. Prices change; recheck before relying on them.

## Costs

- **No fixed or up-front cost.** Signing up is free and Bright Data uses a pre-paid wallet: you are only charged for money you deposit. Without a deposit, the free tier simply stops when the credits run out.
- **Free tier:** 5,000 credits/month, renewing on the 1st, no commitment. Web Unlocker costs 1 credit per request, so about 5,000 requests/month.
- **Pay-as-you-go (only if you deposit funds):** about $1.50 per 1,000 successful requests; failed requests are not billed. You can set monthly spend limits.
- **Optional monthly plan:** Scale at $499/month (about 383K requests, $1.30/1K extra). You don't need it; skip it.
- **Watch for:** the first sign-up for personal-email accounts asks for a payment method in the zone-creation step, for identity verification only ("you will not be charged"). Custom Web Unlocker features (custom headers, cookies, etc.) switch billing to *all* requests, including failures; this component doesn't use them. This component sends 2 requests when both `markdown` and `html` are requested, so use `formats=("markdown",)` to halve usage.
- Bright Data's own blogs quote other per-1K prices ($0.75 to $1.30); the pricing page is the one to trust.

At about 100 pages a week (~400/month), usage stays inside the free tier.

## 1. Sign up and create a zone

1. Create an account at <https://brightdata.com> (no card needed to sign up).
2. In the Control Panel left menu choose **Web Access**, then **Create API**, and pick **Web Unlocker API**.
3. Name the zone (for example `web_scraper_unlocker`). If prompted to **Add payment method**, complete it; it is verification only.
4. Leave defaults and click **Add API**.
5. Open the zone's **Overview** tab. Copy the **zone name** and the **API key** (the key is shown only once; store it safely, ideally with an expiry date if you create one under Account settings > Add API key).

## 2. Add credentials to the project

From the `workflow-lab` project root:

```bash
cp .env.example .env        # .env is git-ignored; never commit it
```

Edit `.env` (the Bright Data lines):

```
BRIGHTDATA_API_KEY=<key from the zone Overview tab>
BRIGHTDATA_ZONE=<zone name>
```

The library reads environment variables and does not load `.env` itself, so load it into your shell first:

```bash
set -a; source .env; set +a
```

## 3. Verify

```bash
uv run pytest -m integration -k brightdata_live    # one real request, 1 credit
```

It passes when `example.com` comes back as Markdown containing "This domain is for use in documentation examples". Common failures:

| Message | Cause |
|---|---|
| `BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE must be set` | `.env` not loaded in this shell |
| `HTTP 401` | wrong or expired API key |
| `HTTP 400` | wrong zone name |
| `unlocker error [...]` | Bright Data could not unlock the target; see the code in the message |

Usage and remaining credits appear in the Control Panel under the zone and Billing.

## Sources

- <https://brightdata.com/pricing/web-unlocker>
- <https://docs.brightdata.com/general/account/billing-and-pricing/free-tier>
- <https://docs.brightdata.com/products/web-unlocker/quickstart>
- <https://docs.brightdata.com/products/web-unlocker/send-your-first-request>
- <https://docs.brightdata.com/products/web-unlocker/features>
