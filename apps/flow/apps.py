"""The flow app: automations — «when this happens, do that» — and the engine that runs them (WORKBOOK.md).

An automation starts on an event of another app, on a schedule, on a date or by hand, and runs its steps
in one column: other apps' actions and reads, by their operation's name (so it requires no app), a
condition that ends it quietly when not met, and waits.
"""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav

#: The actor prefix of what a run does (``flow_run:<id>``): the outbox keeps it, the loop guard reads it.
RUN_ACTOR = "flow_run:"


class FlowConfig(LiveAppConfig):
    name = "apps.flow"
    label = "flow"
    kind = "app"
    verbose_name = _("Automations")
    # Registered in the shell (ION_ICONS); `git-branch` waits in UI-REQUESTS.md.
    icon = "ion:sync-outline"
    category = Category.ORGANIZATION
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
    summary = _(
        "Rules that run on their own when something happens, on a schedule or by hand: repetitive work, done for you."
    )
    # The store's card says what it does today: it starts when something happens in the business (FLOW-F21), at a
    # time, on a date or by hand, and the assistant drafts one when asked (FLOW-F17).
    description = _(
        "Automations runs the repetitive work for you: when something happens in your business, every day, week or "
        "month at a time, on a date, or when you run it, it does what you told it, such as leaving a task or a note "
        "on a customer's card. Start from a ready-made card or ask the assistant to draft one, allow it only what it "
        "needs, try it without effects, turn it on and read in plain words what it did each time."
    )
    # A salon and a restaurant both automate their follow-ups and their opening and closing chores.
    verticals = ["hair_salon", "restaurant"]
    # Other apps' actions and reads are called by their operation's name, never by their models: an
    # automation that names an app that is off fails with its reason, visible in its history.
    requires = []
    # What another app's reaction records in answer to a run's work keeps the run's actor (base.relay passes it on), so
    # the loop guard follows a chain through that app too (FLOW-F21).
    carried_actors = [RUN_ACTOR]
    default_auto_field = "django.db.models.BigAutoField"
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms). An automation (flow.flow), its steps and
    # the question it waits on (flow.question) are named by their phrases and never by the word: «automatización» shares
    # its stem with «automático» («la respuesta automática»), «pasos» with «pasó» («¿qué pasó con…?», so no «qué paso»
    # nor «de paso») and «pregunta» with its verb («se les pregunta»). A run is its «ejecución» (flow.run), the
    # assistant's draft its «borrador» (flow.draft; «borra», «bórralo» and «borrada» stem apart from it) and a
    # ready-made one an app brings its «receta» or «prefabricada» (flow.recipe).
    assistant_synonyms = (
        (
            "flujo", "flow", "an automation", "a new automation", "the automation", "this automation",
            "that automation", "each automation", "any automation", "the automations", "my automations",
            "your automations", "which automations", "what automations",
            *(f"{one} automatizacion" for one in ("la", "una", "esta", "esa", "cada", "alguna", "ninguna", "otra")),
            *(f"{one} automatizacion" for one in ("nueva", "mi", "tu", "su", "de")),
            *(f"{many} automatizaciones" for many in ("las", "unas", "estas", "esas", "todas", "otras", "que")),
            *(f"{many} automatizaciones" for many in ("cuantas", "mis", "tus", "sus", "nuestras", "de")),
        ),
        ("ejecucion", "ejecuciones", "run", "runs"),
        (
            "step", "steps", "paso a paso",
            *(f"{one} paso" for one in ("el", "un", "ese", "este", "cada", "primer", "ultimo", "otro", "algun")),
            *(f"{one} paso" for one in ("ningun", "mi", "tu", "su")),
            *(f"{many} pasos" for many in ("los", "unos", "esos", "estos", "todos", "otros", "nuevos", "que")),
            *(f"{many} pasos" for many in ("cuantos", "mis", "tus", "sus", "de")),
        ),
        (
            "question", "questions",
            *(f"{one} pregunta" for one in ("la", "una", "esa", "esta", "cada", "primera", "ultima", "otra", "alguna")),
            *(f"{one} pregunta" for one in ("ninguna", "mi", "tu", "su")),
            *(f"{many} preguntas" for many in ("las", "unas", "esas", "estas", "todas", "otras", "nuevas", "que")),
            *(f"{many} preguntas" for many in ("cuantas", "mis", "tus", "sus", "de")),
        ),
        ("borrador", "borradores", "draft", "drafts"),
        ("receta", "recetas", "prefabricada", "prefabricadas", "recipe", "recipes"),
    )
    # Viewing, managing, and answering what an automation asks (FLOW-F29): what is asked of employees,
    # and what is asked of managers.
    permissions = ["flow.view", "flow.manage", "flow.answer", "flow.answer_manager"]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). An automation acts
    # in the name of the business with nobody watching: only the owner and the admin see,
    # change or run them; a manager and an employee only answer the questions asked of their role.
    role_permissions = {
        "hub_owner": ["flow.*"],
        "hub_admin": ["flow.*"],
        "hub_manager": ["flow.answer", "flow.answer_manager"],
        "hub_employee": ["flow.answer"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with `icon =`
    # as the module's own icon.
    navigation = [
        Nav("automations", _("Automations"), "ion:sync-outline", "/flow/automations")
    ]
    # FLOW-F22 and FLOW-F23: the worker runs them every minute as the system (cron in UTC), in each business it
    # serves, in its database and on its scope (base.worker._serve_hub).
    scheduled_tasks = [
        {
            "name": "fire_due",
            "operation": "flow.schedule.fire_due",
            "cron": "* * * * *",
            "catch_up": "collapse",
        },
        {
            "name": "resume_due",
            "operation": "flow.run.resume_due",
            "cron": "* * * * *",
            "catch_up": "collapse",
        },
        # FLOW-F16: the history forgets the finished runs older than 90 days, once an hour.
        {
            "name": "prune",
            "operation": "flow.run.prune",
            "cron": "17 * * * *",
            "catch_up": "collapse",
        },
        # FLOW-F30: the questions nobody answered in time, every minute.
        {
            "name": "expire_questions",
            "operation": "flow.question.expire_due",
            "cron": "* * * * *",
            "catch_up": "collapse",
        },
    ]
