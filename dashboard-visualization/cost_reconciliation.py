def summarize_cost_journal(journal: dict, auto_ledger: dict | None = None) -> dict:
    auto_usage = (auto_ledger or {}).get("entries", [])
    manual_usage = journal.get("usage", [])
    usage = [*auto_usage, *manual_usage]
    actuals = journal.get("actuals", [])
    variances = journal.get("variances", [])

    estimated_by_model: dict[str, float] = {}
    estimated_by_provider: dict[str, float] = {}
    estimated_by_bot: dict[str, float] = {}
    rate_basis_by_model: dict[str, dict] = {}

    for row in usage:
        normalized = normalize_model_key(str(row.get("model", "")))
        registry = pricing_for_model(normalized)
        display_model = registry["displayName"] if registry else (str(row.get("model", "")) or "unknown")
        provider = registry["provider"] if registry else "Other"
        estimate = calculated_cost_for_row(row)
        estimated_by_model[display_model] = estimated_by_model.get(display_model, 0) + estimate
        estimated_by_provider[provider] = estimated_by_provider.get(provider, 0) + estimate
        bot = row.get("bot", "unknown")
        estimated_by_bot[bot] = estimated_by_bot.get(bot, 0) + estimate
        if registry:
            rate_basis_by_model[display_model] = {
                "provider": provider,
                "basis": registry["basis"],
                "source": registry["source"],
                "normalizedKey": normalized,
            }

    actual_by_model: dict[str, float] = {}
    actual_by_provider: dict[str, float] = {}
    for row in actuals:
        model = row.get("model", "unknown")
        provider = row.get("provider") or (model.split("/")[0] if "/" in model else "unknown")
        amount = float(row.get("amount", 0) or 0)
        actual_by_model[model] = actual_by_model.get(model, 0) + amount
        actual_by_provider[provider] = actual_by_provider.get(provider, 0) + amount

    return {
        "usage": usage[-10:],
        "actuals": actuals[-10:],
        "variances": variances,
        "estimatedTotal": round(sum(estimated_by_model.values()), 4),
        "actualTotal": round(sum(actual_by_model.values()), 4),
        "autoUsageCount": len(auto_usage),
        "manualUsageCount": len(manual_usage),
        "estimatedProviders": [
            {"provider": key, "cost": value}
            for key, value in sorted(estimated_by_provider.items(), key=lambda item: item[1], reverse=True)
        ],
        "estimatedModels": [
            {"model": key, "cost": value}
            for key, value in sorted(estimated_by_model.items(), key=lambda item: item[1], reverse=True)
        ],
        "estimatedBots": [
            {"bot": key, "cost": value}
            for key, value in sorted(estimated_by_bot.items(), key=lambda item: item[1], reverse=True)
        ],
        "actualProviders": [
            {"provider": key, "cost": value}
            for key, value in sorted(actual_by_provider.items(), key=lambda item: item[1], reverse=True)
        ],
        "actualModels": [
            {"model": key, "cost": value}
            for key, value in sorted(actual_by_model.items(), key=lambda item: item[1], reverse=True)
        ],
        "rateBasisByModel": rate_basis_by_model,
        "sourcePath": str(COST_JOURNAL_PATH),
        "autoLedgerPath": str(USAGE_LEDGER_PATH),
        "autoSourceRoot": str((auto_ledger or {}).get("sourceRoot", OPENCLAW_AGENTS_ROOT)),
    }


def build_month_ledger(journal: dict, auto_ledger: dict | None = None) -> dict:
    usage = [*((auto_ledger or {}).get("entries", [])), *journal.get("usage", [])]
    legacy_actuals = journal.get("actuals", [])
    provider_actuals = journal.get("providerActuals", [])
    model_actuals = journal.get("modelActuals", [])
    prepaids = journal.get("prepaids", [])

    monthly_models: dict[str, dict[str, dict]] = {}
    weekly_models: dict[str, dict[str, dict[str, dict]]] = {}

    def ensure_model(month_key: str, model: str, provider_hint: str = "") -> dict:
        month_bucket = monthly_models.setdefault(month_key, {})
        meta = model_meta(model, provider_hint)
        key = meta["normalizedKey"]
        if key not in month_bucket:
            month_bucket[key] = {
                "modelKey": key,
                "model": meta["displayModel"],
                "provider": meta["provider"],
                "providerKey": meta["providerKey"],
                "family": meta["family"],
                "basis": meta["basis"],
                "source": meta["source"],
                "estimated": 0.0,
                "actual": None,
                "variance": None,
            }
        return month_bucket[key]

    def ensure_week(month_key: str, week_key: str, model: str, provider_hint: str = "") -> dict:
        month_weeks = weekly_models.setdefault(month_key, {})
        week_bucket = month_weeks.setdefault(week_key, {})
        meta = model_meta(model, provider_hint)
        key = meta["normalizedKey"]
        if key not in week_bucket:
            week_bucket[key] = {
                "modelKey": key,
                "model": meta["displayModel"],
                "provider": meta["provider"],
                "providerKey": meta["providerKey"],
                "family": meta["family"],
                "estimated": 0.0,
                "actual": None,
                "variance": None,
            }
        return week_bucket[key]

    for row in usage:
        month_key = month_key_for_row(row)
        model = str(row.get("model", "")).strip() or "unknown"
        provider_hint = str(row.get("provider", "")).strip()
        estimated = calculated_cost_for_row(row)
        bucket = ensure_model(month_key, model, provider_hint)
        bucket["estimated"] += estimated
        date_str = str(row.get("date", "")).strip()
        if date_str:
            week_key = week_key_for_date(date_str)
            if week_key:
                week_bucket = ensure_week(month_key, week_key, model, provider_hint)
                week_bucket["estimated"] += estimated

    def apply_actual_row(row: dict) -> None:
        month_key = month_key_for_row(row)
        model = str(row.get("model", "")).strip()
        provider_hint = str(row.get("provider", "")).strip()
        if not model:
