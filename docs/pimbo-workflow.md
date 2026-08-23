# Pimbo workflow

UltraBike Automatizacija manages product data through the authenticated Pimbo
web application. It uses a Selenium browser owned by the main window; only one
long-running workflow may control that shared browser at a time.

## Sign in

Save the administrator credentials on the Account page, then sign in. The app
opens Pimbo and retains an encrypted local session for the configured lifetime.
Brand credentials are stored separately and are only used by their matching
upload workflow.

## Product automation

The Upload and Unified Batch pages locate products in Pimbo and apply the
selected changes. Pimbo MagicAI can generate or update:

- product titles;
- descriptions;
- category suggestions;
- translated product copy; and
- specifications.

MagicAI template names are configurable in Settings so they can follow changes
made in the Pimbo account. This automation is distinct from manual LT, EN, and
LV description-template editing on the Descriptions page.

## Orbea

The Orbea page discovers filtered Pimbo products, matches catalogue records,
extracts descriptions, and downloads photos. Its checkpoint can resume an
interrupted run. Review the generated workbook before using its results in a
production batch.

## Safe operation

- Let the active job finish or cancel it before starting another browser job.
- Keep Pimbo open on the page requested by the workflow.
- Do not edit a product manually while an automated step is saving it.
- Use the Activity page and processing history to review results and diagnostics.
