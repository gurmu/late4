import sys

try:
    import semantic_kernel as sk
    print("semantic_kernel version:", getattr(sk, "__version__", "unknown"))

    from semantic_kernel import Kernel
    from semantic_kernel.agents.chat_completion.chat_completion_agent import ChatCompletionAgent
    from semantic_kernel.agents.group_chat.agent_group_chat import AgentGroupChat
    from semantic_kernel.agents.strategies import TerminationStrategy
    from semantic_kernel.connectors.ai.open_ai.services.azure_chat_completion import AzureChatCompletion
    from semantic_kernel.functions import kernel_function

    print("imports ok")
    print("Kernel.add_service signature:", Kernel.add_service)
    print("ChatCompletionAgent:", ChatCompletionAgent)
    print("AgentGroupChat:", AgentGroupChat)
    print("TerminationStrategy:", TerminationStrategy)
    print("AzureChatCompletion:", AzureChatCompletion)
    print("kernel_function:", kernel_function)

except Exception as exc:
    print("SK import check failed:", exc)
    sys.exit(1)
