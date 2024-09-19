"""The main module for the wizard package."""

import os
import sys
from enum import Enum
from typing import Optional, Sequence

from anytree import RenderTree
from rich import print as rich_print
from rich.panel import Panel

from .prompts import get_response_from_menu_prompt
from .utils import EnumDict as State
from .utils import NodeMixinWithNavigation

TEXT_CONFIG_FILENAME_PREFIX = "everyvoice-shared-text"
ALIGNER_CONFIG_FILENAME_PREFIX = "everyvoice-aligner"
PREPROCESSING_CONFIG_FILENAME_PREFIX = "everyvoice-shared-data"
TEXT_TO_SPEC_CONFIG_FILENAME_PREFIX = "everyvoice-text-to-spec"
SPEC_TO_WAV_CONFIG_FILENAME_PREFIX = "everyvoice-spec-to-wav"
TEXT_TO_WAV_CONFIG_FILENAME_PREFIX = "everyvoice-text-to-wav"


class _Step:
    """The main class for steps within a tour.

    Each step must implement the prompt and validate methods.
    This method must save the answer in the response attribute.
    """

    def __init__(self, name: str):
        self.response = None
        self.completed = False
        self.name = name

    def prompt(self):
        """Prompt the user and return the result.

        Raises:
            NotImplementedError: If you don't implement anything, this will be raised
        """
        raise NotImplementedError(
            f"This step ({self.name}) doesn't have a prompt method implemented. Please implement one."
        )

    def sanitize_input(self, response):
        """
        Perform data sanitization of user provided input.
        """
        return response

    def sanitize_paths(self, response):
        """For steps that return path, have sanitize_input call sanitize_paths"""
        # Remove surrounding whitespace
        response = response.strip()
        # Support ~ and ~username path expansions
        response = os.path.expanduser(response)
        return response

    def validate(self, response) -> bool:
        """Validate the response.

        Raises:
            NotImplementedError: _description_
        """
        raise NotImplementedError(
            f"This step ({self.name}) doesn't have a validate method implemented. Please implement one."
        )

    def effect(self):
        """Run some arbitrary code after the step resolves"""
        pass


class Step(_Step, NodeMixinWithNavigation):
    """Just a mixin to allow a tree-based interpretation of steps"""

    def __init__(
        self,
        name: None | Enum | str = None,
        default=None,
        parent=None,
        state_subset=None,
    ):
        if name is None:
            name = getattr(self, "DEFAULT_NAME", "default step name missing")
        name = name.value if isinstance(name, Enum) else name
        super(Step, self).__init__(name)
        self.default = default
        self.parent = parent
        self.state_subset = state_subset
        # state will be added when the Step is added to a Tour
        self.state: Optional[State] = None
        # tour will be added when the Step is added to a Tour
        self.tour: Optional[Tour] = None
        self._validation_failures = 0

    def __repr__(self) -> str:
        return f"{self.name}: {super().__repr__()}"

    def run(self):
        """Prompt the user and save the response to the response attribute.
        If this method returns something truthy, continue, otherwise ask the prompt again.
        """
        self.response = self.prompt()
        self.response = self.sanitize_input(self.response)
        if self.tour is not None and self.tour.trace:
            rich_print(f"{self.name}: '{self.response}'")
        if self.validate(self.response):
            self.completed = True
            try:
                if self.state is not None:
                    self.state[self.name] = self.response
                return self.response
            finally:
                self.effect()
        else:
            self._validation_failures += 1
            if self._validation_failures > 20:
                rich_print(
                    f"ERROR: {self.name} giving up after 20 validation failures."
                )
                sys.exit(1)
            self.run()

    def is_reversible(self):
        """Return True if the step's effects can be reversed, False otherwise.

        Also implement undo if you return True and undoing the step requires state changes.
        """
        return False

    def undo(self):
        """Undo the effects of the step.

        If you implement undo, also implement is_reversible with return True
        """
        self.response = None
        self.completed = False
        if self.state is not None:
            del self.state[self.name]


class RootStep(Step):
    """Dummy step sitting at the root of the tour"""

    DEFAULT_NAME = "Root"

    def run(self):
        pass


class Tour:
    def __init__(
        self,
        name: str,
        steps: list[Step],
        state: Optional[State] = None,
        trace: bool = False,
        debug_state: bool = False,
    ):
        """Create the tour by placing all steps under a dummy root node"""
        self.name = name
        self.state: State = state if state is not None else State()
        self.steps = steps
        self.trace = trace
        self.debug_state = debug_state
        self.root = RootStep()
        self.root.tour = self
        self.determine_state(self.root, self.state)
        self.add_steps(steps, self.root)

    def determine_state(self, step: Step, state: State):
        """Determines the state to use for the step based on the state subset"""
        if step.state_subset is not None:
            if step.state_subset not in state:
                state[step.state_subset] = State()
            step.state = state[step.state_subset]
        else:
            step.state = state

    def add_steps(self, steps: Sequence[Step | list[Step]], parent: Step):
        """Insert steps in front of the other children of parent.

        Steps are added as direct children.
        For sublists of steps, the first is a direct child, the rest are under it.
        """
        for item in reversed(steps):
            if isinstance(item, list):
                step, *children = item
                self.add_step(step, parent)
                self.add_steps(children, step)
            else:
                self.add_step(item, parent)

    def add_step(self, step: Step, parent: Step):
        """Insert a step in the specified position in the tour.

        Args:
            step: The step to add
            parent: The parent to add the step to
        """
        self.determine_state(step, self.state)
        step.tour = self
        children = list(parent.children)
        children.insert(0, step)
        parent.children = children

    def keyboard_interrupt_action(self, node):
        """Handle a keyboard interrupt by asking the user what to do"""
        action = None
        # Three Ctrl-C in a row, we just exist, but two in a row might be an
        # accident so ask again.
        for _ in range(2):
            try:
                action = get_response_from_menu_prompt(
                    "What would you like to do?",
                    [
                        "Go back one step",
                        "Continue",
                        "View the question tree",
                        "Save progress",
                        "Exit",
                    ],
                    return_indices=True,
                )
                break
            except KeyboardInterrupt:
                continue
        if action == 0:
            prev = node.prev()
            if prev.is_reversible():
                prev.undo()
                return prev
            else:
                rich_print(
                    f"Sorry, the effects of the {prev.name} cannot be undone, continuing. If you need to go back, you'll have to restart the wizard."
                )
                return node
        elif action == 1:
            return node
        elif action == 2:
            self.visualize(highlight=node)
            return node
        elif action == 3:
            return node
        else:  # still None, or the highest value in the choice list.
            sys.exit(1)

    def run(self):
        """Run the tour by traversing the tree depth-first"""
        node = self.root
        while node is not None:
            if self.debug_state and node.name != "Root":
                rich_print(self.state)
            if self.trace and node.name != "Root":
                self.visualize(node)
            try:
                node.run()
            except KeyboardInterrupt:
                rich_print("\nKeyboard Interrupt")
                node = self.keyboard_interrupt_action(node)
                continue
            node = node.next()

    def visualize(self, highlight: Optional[Step] = None):
        """Display the tree structure of the tour on stdout"""

        def display(pre: str, name: str) -> str:
            return pre + name.replace(" Step", "").replace(
                "Representation", "Rep."
            ).replace("Root", "Wizard Steps")

        just_width = 4 + max(
            len(display(pre, node.name)) for pre, _, node in RenderTree(self.root)
        )
        text = ""
        for pre, _, node in RenderTree(self.root):
            treestr = display(pre, node.name)
            if highlight is not None:
                if node == highlight:
                    treestr = (
                        "[yellow]" + treestr.ljust(just_width) + "←———" + "[/yellow]"
                    )
                elif node.response is not None:
                    treestr = (
                        "[green]"
                        + (treestr + ":").ljust(just_width)
                        + str(node.response)
                        + "[/green]"
                    )
            text += treestr + "\n"
        rich_print(Panel(text.rstrip()))


class StepNames(Enum):
    name_step = "Name Step"
    contact_name_step = "Contact Name Step"
    contact_email_step = "Contact Email Step"
    dataset_name_step = "Dataset Name Step"
    dataset_permission_step = "Dataset Permission Step"
    output_step = "Output Path Step"
    wavs_dir_step = "Wavs Dir Step"
    filelist_step = "Filelist Step"
    filelist_format_step = "Filelist Format Step"
    validate_wavs_step = "Validate Wavs Step"
    filelist_text_representation_step = "Filelist Text Representation Step"
    target_training_representation_step = (
        "Target Training Representation Step"  # TODO: maybe don't need
    )
    data_has_header_line_step = "Filelist Has Header Line Step"
    basename_header_step = "Basename Header Step"
    text_header_step = "Text Header Step"
    data_has_speaker_value_step = "Data Has Speaker Step"
    speaker_header_step = "Speaker Header Step"
    know_speaker_step = "Know Speaker Step"
    add_speaker_step = "Add Speaker Step"
    data_has_language_value_step = "Data Has Language Step"
    language_header_step = "Language Header Step"
    select_language_step = "Select Language Step"
    text_processing_step = "Text Processing Step"
    g2p_step = "G2P Step"
    symbol_set_step = "Symbol-Set Step"
    sample_rate_config_step = "Sample Rate Config Step"
    audio_config_step = "Audio Config Step"
    sox_effects_step = "SoX Effects Step"
    more_datasets_step = "More Datasets Step"
    config_format_step = "Config Format Step"
