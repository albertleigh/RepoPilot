"""
Tab Item Package
Contains tab widget classes hosted by :class:`TabsManager`.
See ``TABS.md`` for the contract that every tab must satisfy.
"""
from .base_tab import BaseTab
from .base_chat_tab import BaseChatTab
from .chat_tab import ChatTab
from .engineer_chat_tab import EngineerChatTab
from .project_manager_chat_tab import ProjectManagerChatTab
from .welcome_tab import WelcomeTab

__all__ = ['BaseTab', 'BaseChatTab', 'ChatTab', 'EngineerChatTab', 'ProjectManagerChatTab', 'WelcomeTab']
