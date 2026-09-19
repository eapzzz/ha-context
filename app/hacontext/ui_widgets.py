"""Small TUI primitives: one selected item, predictable focus, no network work."""
from __future__ import annotations

from prompt_toolkit.application.current import get_app
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Window, HSplit, VSplit, DynamicContainer, Dimension
from prompt_toolkit.layout.containers import WindowAlign
from prompt_toolkit.mouse_events import MouseEventType
from prompt_toolkit.widgets import RadioList


class InstantList(RadioList):
    """The highlighted row IS the selection, for keyboard and mouse alike."""
    def __init__(self, values, default=None, on_change=None):
        self.on_change = on_change
        super().__init__(values, default=default, select_on_focus=True,
                         open_character='', select_character='›', close_character='',
                         show_scrollbar=True, show_cursor=False)
        self.window.dont_extend_height=lambda: False
        kb=self.control.key_bindings
        @kb.add('pageup')
        def up(event): self.move(-self.page_size())
        @kb.add('pagedown')
        def down(event): self.move(self.page_size())
        @kb.add('home')
        def first(event): self.move(-len(self.values))
        @kb.add('end')
        def last(event): self.move(len(self.values))
        # Keep radio-list typeahead, but commit its highlight immediately.
        from prompt_toolkit.keys import Keys
        @kb.add(Keys.Any)
        def find(event):
            from prompt_toolkit.formatted_text import to_formatted_text, fragment_list_to_text
            indices=list(range(self._selected_index+1,len(self.values)))+list(range(self._selected_index+1))
            for i in indices:
                if fragment_list_to_text(to_formatted_text(self.values[i][1])).casefold().startswith(event.data.casefold()):
                    self._selected_index=i;self._handle_enter();break

    def page_size(self):
        info=self.window.render_info
        return max(1,len(info.displayed_lines)-1) if info else 8

    def _handle_enter(self):
        old=self.current_value
        super()._handle_enter()
        if self.on_change and old!=self.current_value:self.on_change(self.current_value)

    def move(self, amount):
        self._selected_index=max(0,min(len(self.values)-1,self._selected_index+amount))
        self._handle_enter()
        get_app().invalidate()

    def replace(self, values, preferred=None):
        self.values=values or [('', 'No matches')]
        keys=[v[0] for v in self.values]
        selected=preferred if preferred in keys else self.current_value
        self._selected_index=keys.index(selected) if selected in keys else 0
        self.current_value=self.values[self._selected_index][0]
        get_app().invalidate()


def navigation_button(button, active, move):
    """Keep Button semantics/testing while removing dialog-button decoration."""
    button.width=22
    button.window.align=WindowAlign.LEFT
    button.window.style=lambda: ('class:nav.focused' if get_app().layout.has_focus(button)
                                  else 'class:nav.active' if active() else 'class:nav')
    def click(event):
        if event.event_type==MouseEventType.MOUSE_UP and button.handler:
            button.handler()
    def fragments():
        return [('[SetCursorPosition]',''),('',('› ' if active() else '  ')+button.text,click)]
    button.control.text=fragments
    kb=button.control.key_bindings
    @kb.add('up')
    def previous(event):move(-1)
    @kb.add('down')
    def next_(event):move(1)
    @kb.add('right')
    def open_(event):
        if button.handler:button.handler()
    return button


def action_rows(buttons, width):
    """Wrap action buttons instead of making an 80-column viewport overflow."""
    def layout():
        available=max(16,width()); rows=[];row=[];used=0
        for button in buttons:
            wanted=getattr(button,'width',None)
            if not isinstance(wanted,int):wanted=min(available,24)
            wanted=min(wanted,available)
            if row and used+wanted+1>available:
                rows.append(VSplit(row+[Window()],padding=1,height=1));row=[];used=0
            row.append(button);used+=wanted+1
        if row:rows.append(VSplit(row+[Window()],padding=1,height=1))
        return HSplit(rows,padding=0)
    return DynamicContainer(layout)

class CycleChoice:
    """Compact filter that cycles with Enter, click, Left or Right."""
    def __init__(self,values,default=None,on_change=None):
        from prompt_toolkit.widgets import Button
        self.values=values;self.current_value=default or values[0][0];self.on_change=on_change
        self.width=17
        self.button=Button('',handler=lambda:self.move(1),width=self.width,left_symbol=' ',right_symbol=' ')
        original=self.button._get_text_fragments
        def text():
            self.button.text=next((v[1] for v in self.values if v[0]==self.current_value),'All')+' ▾'
            return original()
        self.button.control.text=text
        kb=self.button.control.key_bindings
        @kb.add('left')
        def previous(event):self.move(-1)
        @kb.add('right')
        def next_(event):self.move(1)
    def move(self,delta):
        keys=[k for k,_ in self.values]
        self.current_value=keys[(keys.index(self.current_value)+delta)%len(keys)]
        if self.on_change:self.on_change(self.current_value)
        get_app().invalidate()
    def __pt_container__(self):return self.button.window


def wrap_document(text, width):
    """Reflow prose at word boundaries without rewriting fenced code blocks."""
    import textwrap
    width=max(18,width)
    output=[];paragraph=[];code=False
    def flush():
        if paragraph:
            output.extend(textwrap.wrap(' '.join(paragraph),width=width,break_long_words=True,break_on_hyphens=False))
            paragraph.clear()
    for line in text.splitlines():
        if line.strip().startswith('```'):
            flush();code=not code;output.append(line);continue
        if code or line.startswith(('    ','\t','|')):
            flush();output.append(line);continue
        if not line.strip():
            flush();output.append('');continue
        if line.startswith(('#','- ','* ')):
            flush();output.extend(textwrap.wrap(line,width=width,subsequent_indent='  '));continue
        paragraph.append(line.strip())
    flush()
    return '\n'.join(output)+'\n'
