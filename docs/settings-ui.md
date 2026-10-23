# User settings UI prototype

Standalone HTML/CSS/JS under Front__end/settings, reachable at /frontend/settings/settings.html through Settings links on dashboard, add electricity, history, appliances and analysis. Blue/white PowerTrack theme; responsive form and live summary. Styles reuse the existing history layout with page-specific styling.

Fields follow user_settings: residence_type (unknown/dormitory/apartment/house/other), optional occupants (integer >=1), optional default_unit_price (>0, four decimals), optional default_service_charge (>=0, two decimals), optional monthly_budget (>=0, two decimals). Currency THB and timezone Asia/Bangkok are displayed as fixed context. Blank and explicit zero are visually distinct. No tariff, budget or occupants are pre-assumed. Future backend must validate and derive user_id/timestamps, map blanks to null and keep one row per user.

UI-only: live summary, native numeric validation, trial-submit confirmation, clear form. No API, AI, browser persistence or Google Sheets writes. All draft data disappears on reload; the page clearly labels this. It does not yet prefill Add Electricity or change any previous bills. The final backend must preserve past electricity_records when defaults change.

Verification: JS syntax and whitespace checks pass. Parsed all five existing pages and verified exactly one enabled Settings link per page to the new destination. No full visual/browser interaction verification was performed in this step.
