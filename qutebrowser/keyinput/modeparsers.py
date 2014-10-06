# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2014 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""KeyChainParser for "hint" and "normal" modes.

Module attributes:
    STARTCHARS: Possible chars for starting a commandline input.
"""

from PyQt5.QtCore import pyqtSlot, Qt

from qutebrowser.utils import message
from qutebrowser.config import config
from qutebrowser.keyinput import keyparser
from qutebrowser.utils import usertypes, log, objreg, utils


STARTCHARS = ":/?"
LastPress = usertypes.enum('LastPress', ['none', 'filtertext', 'keystring'])


class NormalKeyParser(keyparser.CommandKeyParser):

    """KeyParser for normalmode with added STARTCHARS detection."""

    def __init__(self, win_id, parent=None):
        super().__init__(win_id, parent, supports_count=True,
                         supports_chains=True)
        self.read_config('normal')

    def __repr__(self):
        return utils.get_repr(self)

    def _handle_single_key(self, e):
        """Override _handle_single_key to abort if the key is a startchar.

        Args:
            e: the KeyPressEvent from Qt.

        Return:
            True if event has been handled, False otherwise.
        """
        txt = e.text().strip()
        if not self._keystring and any(txt == c for c in STARTCHARS):
            message.set_cmd_text(self._win_id, txt)
            return True
        return super()._handle_single_key(e)


class PromptKeyParser(keyparser.CommandKeyParser):

    """KeyParser for yes/no prompts."""

    def __init__(self, win_id, parent=None):
        super().__init__(win_id, parent, supports_count=False,
                         supports_chains=True)
        # We don't want an extra section for this in the config, so we just
        # abuse the prompt section.
        self.read_config('prompt')

    def __repr__(self):
        return utils.get_repr(self)


class HintKeyParser(keyparser.CommandKeyParser):

    """KeyChainParser for hints.

    Attributes:
        _filtertext: The text to filter with.
        _last_press: The nature of the last keypress, a LastPress member.
    """

    def __init__(self, win_id, parent=None):
        super().__init__(win_id, parent, supports_count=False,
                         supports_chains=True)
        self._filtertext = ''
        self._last_press = LastPress.none
        self.read_config('hint')
        self.keystring_updated.connect(self.on_keystring_updated)

    def _handle_special_key(self, e):
        """Override _handle_special_key to handle string filtering.

        Return True if the keypress has been handled, and False if not.

        Args:
            e: the KeyPressEvent from Qt.

        Return:
            True if event has been handled, False otherwise.

        Emit:
            keystring_updated: Emitted when keystring has been changed.
        """
        log.keyboard.debug("Got special key 0x{:x} text {}".format(
            e.key(), e.text()))
        hintmanager = objreg.get('hintmanager', scope='tab',
                                 window=self._win_id, tab='current')
        if e.key() == Qt.Key_Backspace:
            log.keyboard.debug("Got backspace, mode {}, filtertext '{}', "
                               "keystring '{}'".format(self._last_press,
                                                       self._filtertext,
                                                       self._keystring))
            if self._last_press == LastPress.filtertext and self._filtertext:
                self._filtertext = self._filtertext[:-1]
                hintmanager.filter_hints(self._filtertext)
                return True
            elif self._last_press == LastPress.keystring and self._keystring:
                self._keystring = self._keystring[:-1]
                self.keystring_updated.emit(self._keystring)
                return True
            else:
                return super()._handle_special_key(e)
        elif config.get('hints', 'mode') != 'number':
            return super()._handle_special_key(e)
        elif not e.text():
            return super()._handle_special_key(e)
        else:
            self._filtertext += e.text()
            hintmanager.filter_hints(self._filtertext)
            self._last_press = LastPress.filtertext
            return True

    def handle(self, e):
        """Handle a new keypress and call the respective handlers.

        Args:
            e: the KeyPressEvent from Qt

        Emit:
            keystring_updated: If a new keystring should be set.
        """
        handled = self._handle_single_key(e)
        if handled and self._keystring:
            # A key has been added to the keystring (Match.partial)
            self.keystring_updated.emit(self._keystring)
            self._last_press = LastPress.keystring
            return handled
        elif handled:
            # We handled the key but the keystring is empty. This happens when
            # match is Match.definitive, so a keychain has been completed.
            self._last_press = LastPress.none
            return handled
        else:
            # We couldn't find a keychain so we check if it's a special key.
            return self._handle_special_key(e)

    def execute(self, cmdstr, keytype, count=None):
        """Handle a completed keychain."""
        if not isinstance(keytype, self.Type):
            raise TypeError("Type {} is no Type member!".format(keytype))
        if keytype == self.Type.chain:
            hintmanager = objreg.get('hintmanager', scope='tab',
                                     window=self._win_id, tab='current')
            hintmanager.fire(cmdstr)
        else:
            # execute as command
            super().execute(cmdstr, keytype, count)

    def update_bindings(self, strings):
        """Update bindings when the hint strings changed.

        Args:
            strings: A list of hint strings.
        """
        self.bindings = {s: s for s in strings}
        self._filtertext = ''

    @pyqtSlot(str)
    def on_keystring_updated(self, keystr):
        """Update hintmanager when the keystring was updated."""
        hintmanager = objreg.get('hintmanager', scope='tab',
                                 window=self._win_id, tab='current')
        hintmanager.handle_partial_key(keystr)
