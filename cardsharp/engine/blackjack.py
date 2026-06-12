"""
Blackjack engine implementation.

This module provides the BlackjackEngine class, which implements the
CardsharpEngine interface for the game of blackjack.

Since beads-i2s.2 the engine is a translation layer over the Rust fast
core's interactive session API (cardsharp_core.Session): rounds run on
the SAME rules implementation as the batch simulator -- real peek and
insurance semantics, splits, surrender, cut-card behavior -- and this
class translates session steps into engine events and adapter calls.
The immutable GameState remains the engine's public view model (the API
layer reads and occasionally mutates it), but no game rules live here.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from cardsharp.adapters import PlatformAdapter
from cardsharp.blackjack.action import Action
from cardsharp.blackjack.console import card_name, hand_value
from cardsharp.blackjack.rules import Rules
from cardsharp.engine.base import CardsharpEngine
from cardsharp.events import EngineEventType
from cardsharp.state import DealerState, GameStage, GameState, HandState, PlayerState

# Sessions meter their own per-seat money from a uniform starting
# bankroll; the engine is the bankroll authority (per-player balances
# live in GameState), so the session just gets a bankroll high enough
# that its internal affordability checks never bind.
_SESSION_BANKROLL = 1e12

_ACTIONS_BY_NAME = {a.value: a for a in Action}


def _build_rules(config: Dict[str, Any]) -> Rules:
    """Map the engine's config dicts onto a cardsharp Rules object."""
    rules_cfg = config.get("rules", {})
    dealer_cfg = config.get("dealer_rules", {})
    deck_count = config.get("deck_count", rules_cfg.get("deck_count", 6))
    hit_soft_17 = rules_cfg.get(
        "dealer_hit_soft_17", not dealer_cfg.get("stand_on_soft_17", True)
    )
    return Rules(
        blackjack_payout=rules_cfg.get("blackjack_pays", 1.5),
        dealer_hit_soft_17=hit_soft_17,
        dealer_peek=dealer_cfg.get("peek_for_blackjack", True),
        allow_split=rules_cfg.get("allow_split", True),
        allow_double_down=rules_cfg.get("allow_double_down", True),
        allow_double_after_split=rules_cfg.get("allow_double_after_split", True),
        allow_insurance=rules_cfg.get("offer_insurance", True),
        allow_surrender=rules_cfg.get("allow_surrender", True),
        allow_resplitting=rules_cfg.get("allow_resplitting", False),
        num_decks=deck_count,
        min_bet=rules_cfg.get("min_bet", 5.0),
        max_bet=rules_cfg.get("max_bet", 1000.0),
        insurance_payout=rules_cfg.get("insurance_payout", 2.0),
        penetration=rules_cfg.get("penetration", 0.75),
        max_splits=rules_cfg.get("max_splits", 3),
    )


class BlackjackEngine(CardsharpEngine):
    """
    Engine implementation for Blackjack.

    Public surface (methods, emitted events, GameState view, adapter
    interplay) is unchanged from the pre-session engine; internally every
    round is played by the fast core through a resumable session, so the
    engine cannot drift from the simulator's parity-proven rules.
    """

    def __init__(self, adapter: PlatformAdapter, config: Dict[str, Any] = None):
        super().__init__(adapter, config)
        self.dealer_rules = self.config.get("dealer_rules", {"stand_on_soft_17": True})
        self.deck_count = self.config.get("deck_count", 6)
        self.rules = self.config.get(
            "rules",
            {
                "blackjack_pays": 1.5,
                "deck_count": self.deck_count,
                "dealer_hit_soft_17": not self.dealer_rules.get(
                    "stand_on_soft_17", True
                ),
                "allow_double_after_split": True,
                "allow_surrender": True,
                "allow_late_surrender": False,
            },
        )
        self.rules_obj = _build_rules(self.config)
        self.state: GameState = GameState(rules=self.rules)

        self._session = None
        self._session_seats = 0
        self._pending_bets: Dict[str, float] = {}
        self._external_actions: Optional[asyncio.Queue] = None
        self._current_decision_player: Optional[str] = None
        self._round_active = False

    # -- lifecycle ---------------------------------------------------------

    async def initialize(self) -> None:
        await super().initialize()
        self.event_bus.emit(
            EngineEventType.ENGINE_INIT,
            {
                "engine_type": "blackjack",
                "config": self.config,
                "timestamp": time.time(),
            },
        )

    async def shutdown(self) -> None:
        self._close_session()
        self.event_bus.emit(EngineEventType.ENGINE_SHUTDOWN, {"timestamp": time.time()})
        await super().shutdown()

    async def start_game(self) -> None:
        self._close_session()
        self.state = GameState(rules=self.rules)
        self.event_bus.emit(
            EngineEventType.GAME_CREATED,
            {"game_id": self.state.id, "rules": self.rules, "timestamp": time.time()},
        )
        self.state = self._with_stage(GameStage.WAITING_FOR_PLAYERS)
        self.event_bus.emit(
            EngineEventType.GAME_STARTED,
            {"game_id": self.state.id, "timestamp": time.time()},
        )

    async def add_player(self, name: str, balance: float = 1000.0) -> str:
        player = PlayerState(name=name, balance=balance)
        players = list(self.state.players) + [player]
        self.state = self._replace(players=players)
        self.event_bus.emit(
            EngineEventType.PLAYER_JOINED,
            {
                "game_id": self.state.id,
                "player_id": player.id,
                "player_name": name,
                "balance": balance,
                "timestamp": time.time(),
            },
        )
        if len(players) == 1:
            self.state = self._with_stage(GameStage.PLACING_BETS)
        return player.id

    # -- betting and the round drive --------------------------------------

    async def place_bet(self, player_id: str, amount: float) -> None:
        if self.state.stage != GameStage.PLACING_BETS:
            raise ValueError("Cannot place bet at this stage")
        player = self._player(player_id)
        if player is None:
            raise ValueError(f"Player {player_id} not found")
        if amount > player.balance:
            raise ValueError("Bet exceeds balance")

        self._pending_bets[player_id] = amount
        # Debit the balance and seat an (empty) hand, as the old engine's
        # bet transition did.
        self._update_player(
            player_id,
            balance=player.balance - amount,
            hands=[HandState(bet=amount)],
        )
        self.event_bus.emit(
            EngineEventType.PLAYER_BET,
            {
                "game_id": self.state.id,
                "round_id": str(self.state.round_number),
                "player_id": player_id,
                "player_name": player.name,
                "amount": amount,
                "previous_balance": player.balance,
                "new_balance": player.balance - amount,
                "timestamp": time.time(),
            },
        )

        if all(p.id in self._pending_bets for p in self.state.players):
            await self._play_round()

    async def execute_player_action(self, player_id: str, action: str) -> None:
        """External action push (the API layer's execute_action path).

        The round drive accepts whichever arrives first: an answer from
        the adapter or an externally pushed action for the player whose
        decision is pending.
        """
        if not self._round_active or self._external_actions is None:
            raise ValueError("Not player's turn")
        if player_id != self._current_decision_player:
            raise ValueError("Not player's turn")
        try:
            parsed = Action[action.upper()]
        except KeyError as exc:
            raise ValueError(f"Unknown action '{action}'") from exc
        await self._external_actions.put(parsed)

    async def render_state(self) -> None:
        await self.adapter.render_game_state(self.state.to_adapter_format())

    # -- internals ---------------------------------------------------------

    def _player(self, player_id: str) -> Optional[PlayerState]:
        for player in self.state.players:
            if player.id == player_id:
                return player
        return None

    def _replace(self, **changes) -> GameState:
        from dataclasses import replace

        return replace(self.state, **changes)

    def _with_stage(self, stage: GameStage) -> GameState:
        return self._replace(stage=stage)

    def _update_player(self, player_id: str, **changes) -> None:
        from dataclasses import replace

        players = [
            replace(p, **changes) if p.id == player_id else p
            for p in self.state.players
        ]
        self.state = self._replace(players=players)

    def _ensure_session(self) -> None:
        from cardsharp.fastsim import open_session

        seats = len(self.state.players)
        if self._session is not None and self._session_seats == seats:
            return
        self._close_session()
        self._session = open_session(
            self.rules_obj,
            n_players=seats,
            bankroll=_SESSION_BANKROLL,
            seed=self.config.get("seed"),
            cards=self.config.get("card_stream"),  # test hook: injected deal
        )
        self._session_seats = seats
        self.event_bus.emit(
            EngineEventType.SHUFFLE,
            {
                "game_id": self.state.id,
                "deck_count": self.rules_obj.num_decks,
                "cards_remaining": self.rules_obj.num_decks * 52,
                "timestamp": time.time(),
            },
        )

    def _close_session(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
            self._session_seats = 0

    async def _play_round(self) -> None:
        self._ensure_session()
        roster = list(self.state.players)
        bets = [self._pending_bets[p.id] for p in roster]

        self.state = self._with_stage(GameStage.DEALING)
        self.event_bus.emit(
            EngineEventType.ROUND_STARTED,
            {
                "game_id": self.state.id,
                "round_id": str(self.state.round_number),
                "player_count": len(roster),
                "timestamp": time.time(),
            },
        )

        self._round_active = True
        self._external_actions = asyncio.Queue()
        try:
            step = self._session.begin_round(bets)
            self._emit_initial_deal(step, roster)
            self._project_step(step, roster)
            await self.render_state()

            while step.phase != "round_over":
                step = await self._answer_step(step, roster)
                self._project_step(step, roster)
                await self.render_state()
        finally:
            self._round_active = False
            self._current_decision_player = None
            self._external_actions = None

        record = step.result
        self._emit_dealer_reveal(record)
        self._settle_round(record, roster, bets)

    async def _answer_step(self, step, roster):
        """Resolve one pending decision: adapter answer or external push."""
        seat = step.seat
        player = roster[seat]
        self._current_decision_player = player.id

        if step.phase == "insurance":
            valid = [Action.INSURANCE, Action.STAND]
        else:
            valid = [_ACTIONS_BY_NAME[name] for name in step.valid_actions]

        self.event_bus.emit(
            EngineEventType.PLAYER_DECISION_NEEDED,
            {
                "game_id": self.state.id,
                "round_id": str(self.state.round_number),
                "player_id": player.id,
                "player_name": player.name,
                "valid_actions": valid,
                "timestamp": time.time(),
            },
        )

        action = await self._request_action(player, valid)
        if step.phase == "insurance":
            answer = "insure" if action == Action.INSURANCE else "decline"
        elif step.phase == "early_surrender":
            answer = "surrender" if action == Action.SURRENDER else "stand"
        else:
            answer = action.value if action.value in step.valid_actions else "stand"

        next_step = self._session.apply(answer)
        self._current_decision_player = None
        self._emit_action_cards(action, player, seat, step, next_step)
        self.event_bus.emit(
            EngineEventType.PLAYER_ACTION,
            {
                "game_id": self.state.id,
                "round_id": str(self.state.round_number),
                "player_id": player.id,
                "player_name": player.name,
                "action": action.name,
                "timestamp": time.time(),
                "next_stage": self.state.stage.name,
            },
        )
        return next_step

    async def _request_action(self, player: PlayerState, valid: List[Action]):
        """Race the adapter's answer against an external execute_action."""
        adapter_task = asyncio.ensure_future(
            self.adapter.request_player_action(
                player_id=player.id,
                player_name=player.name,
                valid_actions=valid,
                timeout_seconds=30.0,
            )
        )
        external_task = asyncio.ensure_future(self._external_actions.get())
        done, pending = await asyncio.wait(
            {adapter_task, external_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        winner = done.pop()
        try:
            return winner.result()
        except asyncio.TimeoutError:
            return await self.adapter.handle_timeout(
                player_id=player.id, player_name=player.name
            )

    # -- card events (the old transitions layer emitted these; the
    # translation layer reconstructs them from session steps) -----------

    @staticmethod
    def _hands_of(step, seat_index):
        source = step.result.players if step.phase == "round_over" else step.players
        return [list(h) for h in source[seat_index].hands]

    def _emit_card(
        self, card, player=None, hand_index=0, is_hole=False, before=0, after=0
    ) -> None:
        data = {
            "game_id": self.state.id,
            "card": card,
            "is_dealer": player is None,
            "hand_value_before": before,
            "hand_value_after": after,
            "timestamp": time.time(),
        }
        if player is None:
            data["is_hole_card"] = is_hole
        else:
            data["player_id"] = player.id
            data["player_name"] = player.name
            data["hand_index"] = hand_index
        self.event_bus.emit(EngineEventType.CARD_DEALT, data)

    def _emit_initial_deal(self, step, roster) -> None:
        """One CARD_DEALT per dealt card, in table order: first pass to
        each seat, dealer upcard, second pass, then the facedown hole
        card as '?' (the old transitions layer leaked the real hole card
        into this event; the session never exposes it early)."""
        first_two = [self._hands_of(step, i)[0][:2] for i in range(len(roster))]
        upcard = (
            step.result.dealer_cards[0]
            if step.phase == "round_over"
            else step.dealer_cards[0]
        )
        for deal_pass in (0, 1):
            for seat, base in enumerate(roster):
                cards = first_two[seat]
                self._emit_card(
                    card_name(cards[deal_pass]),
                    player=base,
                    before=hand_value(cards[:deal_pass]),
                    after=hand_value(cards[: deal_pass + 1]),
                )
            if deal_pass == 0:
                up_value = hand_value([upcard])
                self._emit_card(card_name(upcard), after=up_value)
            else:
                up_value = hand_value([upcard])
                self._emit_card("?", is_hole=True, before=up_value, after=up_value)

    def _emit_action_cards(self, action, player, seat, prev_step, next_step) -> None:
        """Cards drawn by the applied action. Keyed on the action (hit
        and double draw one to the acting hand; split draws one to each
        affected hand) and guarded by actual growth, so refused draws
        (the split-ace quirks) emit nothing."""
        if action not in (Action.HIT, Action.DOUBLE, Action.SPLIT):
            return
        prev_hands = self._hands_of(prev_step, seat)
        hands = self._hands_of(next_step, seat)
        if action == Action.SPLIT:
            if len(hands) <= len(prev_hands):
                return
            affected = [prev_step.hand_index, len(hands) - 1]
        else:
            hand_index = prev_step.hand_index
            if len(hands[hand_index]) <= len(prev_hands[hand_index]):
                return
            affected = [hand_index]
        for index in affected:
            codes = hands[index]
            self._emit_card(
                card_name(codes[-1]),
                player=player,
                hand_index=index,
                before=hand_value(codes[:-1]),
                after=hand_value(codes),
            )

    def _emit_dealer_reveal(self, record) -> None:
        """The hole card turns over, then any dealer draws."""
        cards = list(record.dealer_cards)
        self._emit_card(
            card_name(cards[1]),
            is_hole=True,
            before=hand_value(cards[:1]),
            after=hand_value(cards[:2]),
        )
        for i in range(2, len(cards)):
            self._emit_card(
                card_name(cards[i]),
                before=hand_value(cards[:i]),
                after=hand_value(cards[: i + 1]),
            )

    def _project_step(self, step, roster) -> None:
        """Refresh the GameState view from a session step."""
        from dataclasses import replace

        final = step.phase == "round_over"
        if final:
            seats = step.result.players
            dealer_cards = list(step.result.dealer_cards)
        else:
            seats = step.players
            dealer_cards = list(step.dealer_cards)

        players = []
        for i, base in enumerate(roster):
            seat = seats[i]
            # Final records zero out paid bets; show the original wagers.
            bets = list(seat.original_bets) if final else list(seat.bets)
            hands = [
                HandState(cards=[card_name(c) for c in cards], bet=bet)
                for cards, bet in zip(([list(h) for h in seat.hands]), bets)
            ]
            current = self._player(base.id)
            balance = current.balance if current else base.balance
            hand_index = (
                step.hand_index
                if (not final and step.seat == i and step.hand_index is not None)
                else 0
            )
            players.append(
                replace(
                    base,
                    balance=balance,
                    hands=hands,
                    current_hand_index=hand_index,
                )
            )

        # Mid-round the session exposes only the upcard (the hole card
        # never crosses until round_over); a "?" placeholder keeps the
        # two-card shape so hide_second_card masking engages. The dict's
        # dealer "value" counts the placeholder as 10 -- a constant,
        # leak-free offset that only the masked pre-reveal view carries
        # (the old engine put the TRUE total here, leaking the hole card
        # to any adapter that forwarded the state).
        names = [card_name(c) for c in dealer_cards]
        if not final and len(names) == 1:
            names.append("?")
        dealer = DealerState(
            hand=HandState(cards=names),
            visible_card_count=len(names) if final else 1,
        )
        if final:
            stage = GameStage.END_ROUND
        elif step.phase == "insurance":
            stage = GameStage.INSURANCE
        else:
            stage = GameStage.PLAYER_TURN
        self.state = self._replace(
            players=players,
            dealer=dealer,
            stage=stage,
            current_player_index=step.seat if not final else 0,
        )

    def _settle_round(self, record, roster, bets) -> None:
        """Apply round results to balances, announce, and reset for the
        next round."""
        from dataclasses import replace

        # The balance was debited by the bet at place_bet time; the
        # record's net is relative to the round start, so the final
        # balance is (debited + bet) + net.
        new_balances = {
            base.id: (self._player(base.id).balance + bets[i]) + record.players[i].net
            for i, base in enumerate(roster)
        }
        self.state = self._replace(
            players=[
                replace(p, balance=new_balances.get(p.id, p.balance))
                for p in self.state.players
            ]
        )

        self.event_bus.emit(
            EngineEventType.ROUND_ENDED,
            {
                "game_id": self.state.id,
                "round_id": str(self.state.round_number),
                "timestamp": time.time(),
                "results": {
                    p.id: {"name": p.name, "balance": p.balance}
                    for p in self.state.players
                },
                "dealer": {
                    "hand": {"cards": [str(c) for c in self.state.dealer.hand.cards]}
                },
            },
        )

        # Prepare the next round: clear hands and bets, back to betting.
        self._pending_bets.clear()
        cleared = [
            replace(p, hands=[], current_hand_index=0) for p in self.state.players
        ]
        self.state = self._replace(
            players=cleared,
            dealer=DealerState(),
            stage=GameStage.PLACING_BETS,
            round_number=self.state.round_number + 1,
            current_player_index=0,
        )

    def _get_valid_actions(self) -> List[Action]:
        """Valid actions for the pending decision, if any (compatibility
        helper; the session provides these per step)."""
        return []
