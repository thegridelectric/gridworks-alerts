from gwalert.types._aliases import GwMessage


class Glitch(GwMessage):
    from_g_node_alias: str
    type: str
    summary: str
