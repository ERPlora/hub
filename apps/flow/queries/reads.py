"""What the reads of Automations share with its writes: who may see, manage and answer, what only the platform
runs, and where an «Ask the assistant» step keeps its conversation."""

VIEW = "flow.view"
MANAGE = "flow.manage"
#: Run only by the platform (events.py and the scheduled tasks): no role holds it.
SYSTEM = "flow.system"
#: FLOW-F29: answering what is asked of employees, and of managers; whoever manages answers everything.
ANSWER = "flow.answer"
ANSWER_MANAGER = "flow.answer_manager"
#: The permission each role of «Ask someone first» asks for ('' = whoever runs the business).
ROLE_PERMISSION = {"": MANAGE, "manager": ANSWER_MANAGER, "employee": ANSWER}
#: Where a step's conversation lives while the assistant thinks: no step id starts with «_» (``StepId``).
TURN = "_turn"
