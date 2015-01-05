import threading
import re
import os
import sublime, sublime_plugin

from cc.cc import *

opt = [
  "-Wall",
  "-I/Users/zixunlv/codes/A2/src",
  "-I/usr/local/opt/llvm/include",
]

language_regex = re.compile("(?<=source\.)[\w+#]+")
drivers = {
  "c++": True,
  "c": True,
  "objc": True,
  "objc++": True,
}

def get_unsaved_files(view):
  buffer = None
  if view.is_dirty():
      buffer = [(view.file_name(), view.substr(sublime.Region(0, view.size())))]
  return buffer


def can_complete(view):
  caret = view.sel()[0].a
  language = language_regex.search(view.scope_name(caret))
  if language != None:
    language = language.group(0)

  return language in drivers


class WraperComplete(object):

  def __init__(self):
    self._dispatch_map = {
      CXCursorKind.FIELD_DECL: self._field,
      CXCursorKind.FUNCTION_DECL: self._function,
      CXCursorKind.MACRO_DEFINITION: self._macro,
      CXCursorKind.NOT_IMPLEMENTED: self._not_implemented,
      CXCursorKind.VAR_DECL: self._var,
      CXCursorKind.PARM_DECL: self._var,
      CXCursorKind.TYPEDEF_DECL: self._typdef,
    }


  def get_entry(self, v):
    if v.kind in self._dispatch_map:
      func = self._dispatch_map[v.kind]
      return func(v)
    return self._unknow(v)


  def _unknow(self, v):
    print("unknow kind: ", v.kind, v.name)
    trigger, contents = self._attach(v)
    return (trigger, contents)


  def _attach(self, v, begin_idx=0):
    decl = ""
    contents = ""
    holder_idx = 1
    for i in range(begin_idx, v.length):
      trunk = v[i]
      value = trunk.value
      if trunk.kind == CXCompletionChunkKind.Placeholder:
        value = "${%d:%s}" % (holder_idx, value)
        holder_idx += 1
      contents += value
      decl += trunk.value
    return decl, contents


  def _typdef(self, v):
    _v, contents = self._attach(v)
    trigger = "%s\t%s" % (_v, "Typedef")
    return (trigger, contents)


  def _function(self, v):
    return_type = v[0].value
    func_decl, contents = self._attach(v, 1)
    trigger = "%s\t%s" % (func_decl, return_type)
    return (trigger, contents)


  def _not_implemented(self, v):
    _v, contents = self._attach(v)
    trigger = "%s\t%s" % (_v, "KeyWord")
    return (trigger, contents)


  def _macro(self, v):
    macro, contents = self._attach(v)
    trigger = "%s\t%s" % (macro, "Macro")
    return (trigger, contents)


  def _var(self, v):
    var = v.name
    var_type = v[0].value
    trigger = "%s\t%s" % (var, var_type)
    return (trigger, var)

  def _field(self, v):
    return self._var(v)


class Complete(object):
  symbol_map = {}
  wraper = WraperComplete()
  member_regex = re.compile(r"(([a-zA-Z_]+[0-9_]*)|([\)\]])+)((\.)|(->))$")

  @staticmethod
  def get_symbol(file_name, unsaved_files):
    self = Complete    
    if file_name in self.symbol_map:
      return self.symbol_map[file_name]
    else:
      sym = CCSymbol(file_name, opt, unsaved_files)
      self.symbol_map[file_name] = sym
      return sym

  @staticmethod
  def del_symbol(file_name):
    self = Complete
    if file_name in self.symbol_map:
      del self.symbol_map[file_name]

  @staticmethod
  def is_member_completion(view):
    # fast check
    point = view.sel()[0].begin() - 1
    if point < 0:
      return False

    cur_char = view.substr(point)
    # print "cur_char:", cur_char
    if cur_char and cur_char != "." and cur_char != ">" and cur_char != "]":
      return False

    caret= view.sel()[0].begin()
    line = view.substr(sublime.Region(view.line(caret).a, caret))
    return Complete.member_regex.search(line) != None


class CCAutoComplete(sublime_plugin.EventListener):
  complete_result = None
  t = False

  def on_modified(self, view):
    if can_complete(view) and Complete.is_member_completion(view):
      self.per_complete()

  def per_complete(self):
    sublime.active_window().run_command("hide_auto_complete")
    self.is_trigger = True
    def hack2():
      sublime.active_window().run_command("auto_complete")
    sublime.set_timeout(hack2, 1)
  
  
  def on_query_completions(self, view, prefix, locations):
    line, col = view.rowcol(locations[0])
    line += 1
    col += 1

    file_name = view.file_name()

    if not can_complete(view):
      return

    if self.complete_result != None:
      ret = (self.complete_result, sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)
      self.complete_result = None
      return ret

    elif not self.t or not self.t.is_alive():
      unsaved_files = get_unsaved_files(view)
      def do_complete():
        sym = Complete.get_symbol(file_name, unsaved_files)
        results = sym.complete_at(line, col, unsaved_files)
        complete = results.match(prefix)
        ret = []
        print("prefix: %s len:%d" % (prefix, len(complete)))
        for i, name, v in complete:
          entry = Complete.wraper.get_entry(v)
          # print("[%d] %s  %s" % (i, entry[1], v.kind))
          ret.append(entry)
        self.complete_result = ret
        self.per_complete()

      self.t = threading.Thread(target=do_complete)
      self.t.start()
      return None

    else:
      print("complete busy!")
      return None