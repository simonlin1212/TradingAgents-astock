# TradingAgents/graph/setup.py

from typing import Any, Dict
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic


# 需要综合全局信息做决策的两个节点走 deep 档，其余走 quick 档。
# 这是**没有单独配置角色模型时**的默认分档，与原行为一致。
DEEP_ROLES = frozenset({"research_manager", "portfolio_manager"})

# 可以单独指定模型的角色（config["role_llms"] 的合法键）。
# 单列出来是为了把配错的角色名当场报出来，而不是静默忽略、让人以为配置生效了。
ROLE_KEYS = (
    "market", "social", "news", "fundamentals", "policy", "hot_money", "lockup",
    "quality_gate", "bull", "bear", "research_manager", "trader",
    "risk_aggressive", "risk_neutral", "risk_conservative", "portfolio_manager",
)


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        resolve_llm=None,
    ):
        """Initialize with required components.

        resolve_llm: 可选，`role -> llm | None` 的查表函数。返回 None 表示该角色
        没有单独配置，回落到 quick/deep 两档——不传就是完全的原行为（#39）。
        """
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self._resolve_llm = resolve_llm

    def llm_for(self, role: str) -> Any:
        """取某个角色该用的 LLM。没单独配就回落到 quick/deep 两档。"""
        if self._resolve_llm is not None:
            llm = self._resolve_llm(role)
            if llm is not None:
                return llm
        return self.deep_thinking_llm if role in DEEP_ROLES else self.quick_thinking_llm

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals", "policy", "hot_money", "lockup"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst (technical analysis)
                - "social": Social media / sentiment analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
                - "policy": Policy analyst (A-stock specific)
                - "hot_money": Hot money / capital flow tracker (A-stock specific)
                - "lockup": Lockup expiry / reduction watcher (A-stock specific)
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(self.llm_for("market"))
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(self.llm_for("social"))
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(self.llm_for("news"))
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(self.llm_for("fundamentals"))
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        if "policy" in selected_analysts:
            analyst_nodes["policy"] = create_policy_analyst(self.llm_for("policy"))
            delete_nodes["policy"] = create_msg_delete()
            tool_nodes["policy"] = self.tool_nodes["policy"]

        if "hot_money" in selected_analysts:
            analyst_nodes["hot_money"] = create_hot_money_tracker(self.llm_for("hot_money"))
            delete_nodes["hot_money"] = create_msg_delete()
            tool_nodes["hot_money"] = self.tool_nodes["hot_money"]

        if "lockup" in selected_analysts:
            analyst_nodes["lockup"] = create_lockup_watcher(self.llm_for("lockup"))
            delete_nodes["lockup"] = create_msg_delete()
            tool_nodes["lockup"] = self.tool_nodes["lockup"]

        # Create quality gate node
        quality_gate_node = create_quality_gate(self.llm_for("quality_gate"))

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(self.llm_for("bull"))
        bear_researcher_node = create_bear_researcher(self.llm_for("bear"))
        research_manager_node = create_research_manager(self.llm_for("research_manager"))
        trader_node = create_trader(self.llm_for("trader"))

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.llm_for("risk_aggressive"))
        neutral_analyst = create_neutral_debator(self.llm_for("risk_neutral"))
        conservative_analyst = create_conservative_debator(self.llm_for("risk_conservative"))
        portfolio_manager_node = create_portfolio_manager(self.llm_for("portfolio_manager"))

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Add quality gate + other nodes
        workflow.add_node("Quality Gate", quality_gate_node)
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # Define edges
        # Start with the first analyst
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        # Connect analysts in sequence
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            # Connect to next analyst or to Bull Researcher if this is the last analyst
            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i+1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Quality Gate")

        workflow.add_edge("Quality Gate", "Bull Researcher")

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Conservative Analyst": "Conservative Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Aggressive Analyst": "Aggressive Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )

        workflow.add_edge("Portfolio Manager", END)

        return workflow
