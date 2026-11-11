"""
PC control: the actions Yashi can take on this computer.

registry.py   tool definitions the planner can choose from
planner.py    decides whether a message is a command and which tools to run
agent.py      runs the chosen tools, asks before risky ones (sending messages...)
windows.py    low-level Windows helpers (apps, windows, keyboard, volume)
browser.py    "Yashi's browser": a Chrome window she controls (YouTube Music, WhatsApp Web)
tools_*.py    the tools themselves
"""
