import logging
import traceback

logger = logging.getLogger(__name__)

class IntrospectionEngine:
    def __init__(self, time_utils):
        try:
            self.t = time_utils
        except Exception as e:
            logger.error(f"Failed to initialize IntrospectionEngine: {e}")
            logger.error(traceback.format_exc())
            raise

    def should_introspect(self, state: dict, silence_ms: int) -> bool:
        try:
            if not isinstance(state, dict):
                return False
            
            last_introspection_ms = state.get("last_introspection_ms", 0)
            last_inbound_ms = state.get("last_inbound_ms", 0)
            
            # If we've never introspected, do it if there's been an inbound message
            if last_introspection_ms == 0 and last_inbound_ms > 0:
                return True
            
            # If enough time has passed since the last introspection
            if self.t.now_ms() - last_introspection_ms > silence_ms:
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error in should_introspect: {e}")
            logger.error(traceback.format_exc())
            return False

    def build_block(self) -> str:
        return (
            "SYSTEM: It has been a while since we last spoke. "
            "Perform a self-reflection by summarizing our recent interactions, "
            "reviewing your existing notes, and identifying any new rules or core memories that have emerged. "
            "This is a background task; do not greet the user. Just provide the analysis."
        )
