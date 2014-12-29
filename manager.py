__author__ = 'tunacom'

import enum
import hashlib
import os
import pickle
import sys
import shutil
import time

MANAGER_DIRNAME = 'SuaveSave'
POLL_INTERVAL = 0.2
ACTIVE_POLL_INTERVAL = 0.1
MAX_ACTIVE_POLLS = 10
HELP_TEXT = '''To navigate the menus, enter a choice number or keyword.'''


class MenuState(enum.Enum):
  """Enum representing menu state."""
  MODE_SELECT = 0

  # Base modes.
  CREATE = 1
  LOAD = 2
  AUTOLOAD = 3
  REORDER = 4
  DELETE = 5

  # Profile modes.
  PROFILE = 10
  SELECT_PROFILE = 11
  CREATE_PROFILE = 12
  SET_DEFAULT_PROFILE = 13
  DELETE_PROFILE = 14

  # Special modes.
  HELP = 99
  EXIT = 100


class ManagerError(Exception):
  """Base class for manager exceptions."""
  pass


class NoProfileException(ManagerError):
  """Exception to be raised if no profiles exist."""
  pass


class NoSaveException(ManagerError):
  """Exception to be raised if no saves exist."""
  pass


class Save(object):
  """Simple class representing a save."""
  def __init__(self, name, tags=None):
    if not tags:
      tags = []

    self.name = name
    self.tags = tags


class Profile(object):
  """Simple class representing a single profile."""
  def __init__(self, name, game_directory):
    self.name = name
    self.game_directory = game_directory


class ProfileList(object):
  """Simple class representing the list of stored profiles."""
  def __init__(self):
    self.profiles = []
    self.default = 0

  def get_default(self):
    """Return the default profile."""
    if not self.profiles:
      return None

    return self.profiles[self.default]


class Choice(object):
  """Choice for a menu item."""
  def __init__(self, option, display_text, keyword, highlight=False):
    self.option = option
    self.display_text = display_text
    self.keyword = keyword.lower()
    self.highlight = highlight


class Manager(object):
  """The save manager."""
  def __init__(self):
    self.appdata_dir = os.environ['AppData']
    assert os.path.isdir(self.appdata_dir)

    home_dir = os.path.expanduser('~')
    documents_dir = os.path.join(home_dir, 'Documents')

    # Attempt to fall back to My Documents for people who are doing it wrong.
    if not os.path.isdir(documents_dir):
      documents_dir = os.path.join(home_dir, 'My Documents')

    # Try to create if if we're still stuck.
    if not os.path.exists(documents_dir):
      documents_dir = os.path.join(home_dir, 'Documents')
      os.mkdir(documents_dir)

    assert os.path.isdir(documents_dir)

    self.manager_dir = os.path.join(documents_dir, MANAGER_DIRNAME)
    if not os.path.exists(self.manager_dir):
      os.mkdir(self.manager_dir)
      return

    self.profiles_file = os.path.join(self.manager_dir, 'PROFILES')
    if os.path.exists(self.profiles_file):
      handle = open(self.profiles_file, 'rb')
      self.profiles = pickle.load(handle)
    else:
      self.profiles = ProfileList()

    self.profile = None
    self.profile_dir = ''
    self.game_directory = ''

    self.saves = []
    self.saves_file = ''

    profile = self.profiles.get_default()
    if profile:
      self._set_profile(profile)

  # Profile helpers.
  def _set_profile(self, profile):
    self.profile = profile

    profile_subdir = self._hash(profile.name)
    self.profile_dir = os.path.join(self.manager_dir, profile_subdir)
    self.game_directory = profile.game_directory

    self.saves = []
    self.saves_file = os.path.join(self.profile_dir, 'SAVES')

    # Attempt to load the saves file.
    if not os.path.exists(self.saves_file):
      return

    handle = open(self.saves_file, 'rb')
    self.saves = pickle.load(handle)

  # Misc helpers.
  @staticmethod
  def _hash(s):
    """Return a hash of |s|."""
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

  # Menu helpers.
  def _saves_to_choices(self):
    """Simple helper to convert saves to a choice list."""
    if not self.saves:
      raise NoSaveException

    return [Choice(i, s.name, s.name) for i, s in enumerate(self.saves)]

  def _profiles_to_choices(self):
    profiles = self.profiles.profiles
    if not profiles:
      raise NoProfileException

    return [Choice(i, p.name, p.name) for i, p in enumerate(profiles)]

  @staticmethod
  def _get_choice(choices):
    """Have the user select a choice from a list of choices."""
    keyword_lookup_table = {}
    for i, choice in enumerate(choices):
      # Format the item for display in the menu.
      item = choice.display_text
      if choice.keyword != choice.display_text.lower():
        item += ' (%s)' % choice.keyword.upper()

      if choice.highlight:
        item += ' *selected*'

      print('%.2d: %s' % (i, item))
      keyword_lookup_table[choice.keyword] = i

    while True:
      choice = input('enter your choice: ')

      try:
        choice = int(choice)
      except ValueError:
        # Check to see if a keyword was typed instead of an integer.
        try:
          choice = keyword_lookup_table[choice.strip().lower()]
        except ValueError:
          print('invalid selection')
          continue

      if 0 <= choice < len(choices):
        return choices[choice].option

      print('selection must be between 0 and %d' % (len(choices) - 1))

  def _confirm(self, prompt):
    """Display a confirmation prompt and return True if accepted."""
    print(prompt)
    choices = [Choice(True, 'yes', 'y'), Choice(False, 'no', 'n')]
    return self._get_choice(choices)

  # Filesystem helpers.
  def _set_save(self, index):
    """Move a save to the correct directory."""
    backup_dir = os.path.join(self.profile_dir, 'backup')
    if os.path.exists(backup_dir):
      shutil.rmtree(backup_dir)

    if os.path.exists(self.game_directory):
      shutil.move(self.game_directory, backup_dir)

    save_name = self.saves[index].name
    save_dir = os.path.join(self.profile_dir, self._hash(save_name))
    shutil.copytree(save_dir, self.game_directory)

  def _get_last_modified_time_in_profile(self):
    """Get the last time a file under the save directory has been modified."""
    last_time = os.path.getmtime(self.game_directory)
    for root, _, files in os.walk(self.game_directory):
      for file in files:
        current_time = os.path.getmtime(os.path.join(root, file))
        if current_time > last_time:
          last_time = current_time

    return last_time

  def _write_saves_file(self):
    """Write a save file."""
    handle = open(self.saves_file, 'wb')
    pickle.dump(self.saves, handle)

  def _write_profiles_file(self):
    """Write a save file."""
    handle = open(self.profiles_file, 'wb')
    pickle.dump(self.profiles, handle)

  # Menu option handlers.
  def _select(self):
    """Handle the selection state."""
    choices = [
      Choice(MenuState.CREATE, 'create a save', 'create'),
      Choice(MenuState.LOAD, 'load a save', 'load'),
      Choice(MenuState.AUTOLOAD, 'automatically restore a save', 'autoload'),
      Choice(MenuState.REORDER, 'reorder saves', 'reorder'),
      Choice(MenuState.DELETE, 'delete saves', 'delete'),
      Choice(MenuState.PROFILE, 'manage profiles', 'profiles'),
      Choice(MenuState.HELP, 'help', 'help'),
      Choice(MenuState.EXIT, 'quit', 'quit'),
    ]

    next_state = self._get_choice(choices)
    return next_state

  def _create(self):
    """Handle the save creation state."""
    if not os.path.isdir(self.game_directory):
      print('game directory does not exist (%s)' % self.game_directory)
      return MenuState.MODE_SELECT

    name = input('enter a name: ')

    dest_dir = os.path.join(self.profile_dir, self._hash(name))
    if os.path.exists(dest_dir):
      result = self._confirm('a save with this name already exists. overwrite?')
      if not result:
        print('save NOT created')
        return MenuState.MODE_SELECT

      shutil.rmtree(dest_dir)
      for i, save in enumerate(self.saves):
        if save.name == name:
          del self.saves[i]
          break

    shutil.copytree(self.game_directory, dest_dir)

    self.saves.append(Save(name))
    self._write_saves_file()

    print('created save %.2d (%s)' % (len(self.saves) - 1, name))
    return MenuState.MODE_SELECT

  def _load(self):
    """Load a managed save."""
    choices = self._saves_to_choices()
    save_number = self._get_choice(choices)
    self._set_save(save_number)

    return MenuState.MODE_SELECT

  def _autoload(self):
    """Continuously restore a save."""
    choices = self._saves_to_choices()
    save_number = self._get_choice(choices)
    self._set_save(save_number)

    last_time = self._get_last_modified_time_in_profile()

    print('restoring save %d, ctrl+c to stop' % save_number)
    try:
      while True:
        # Poll to see if anything in the save directory has been modified.
        time.sleep(POLL_INTERVAL)
        current_time = self._get_last_modified_time_in_profile()
        if current_time > last_time:
          # The save has been modified, but if it is still saving it is
          # important not to pull the directory out from under the game.
          # This is a hack. Slow, single-file saves may still be interrupted.
          for _ in range(MAX_ACTIVE_POLLS):
            time.sleep(ACTIVE_POLL_INTERVAL)
            last_time = current_time
            current_time = self._get_last_modified_time_in_profile()
            if current_time == last_time:
              # Nothing has been modified since the last poll. We assume that it
              # is done saving, but as mentioned before this can still interrupt
              # an active save.
              break

          self._set_save(save_number)
          last_time = self._get_last_modified_time_in_profile()

    except KeyboardInterrupt:
      pass

    return MenuState.MODE_SELECT

  def _reorder(self):
    print('which save would you like to move?')
    choices = self._saves_to_choices()
    save_number = self._get_choice(choices)

    print('which save should it be moved before?')
    save = self.saves.pop(save_number)
    choices = self._saves_to_choices()
    choices.append(Choice(len(choices), 'end of list', 'end'))
    new_position = self._get_choice(choices)

    self.saves.insert(new_position, save)
    self._write_saves_file()
    return MenuState.MODE_SELECT

  def _delete(self):
    choices = self._saves_to_choices()
    save_number = self._get_choice(choices)

    name = self.saves[save_number].name
    prompt = 'are you sure you want to delete save %d (%s)?' % (save_number,
                                                                name)
    confirmed = self._confirm(prompt)
    if not confirmed:
      print('save has NOT been deleted')
      return MenuState.MODE_SELECT

    save_dir = os.path.join(self.profile_dir, self._hash(name))
    shutil.rmtree(save_dir)
    del self.saves[save_number]
    self._write_saves_file()

    print('save %d (%s) has been permanently deleted' % (save_number, name))
    return MenuState.MODE_SELECT

  # Profile handlers.
  def _profile(self):
    """Select a profile-related option."""
    choices = [
      Choice(MenuState.SELECT_PROFILE, 'select profile', 'select'),
      Choice(MenuState.CREATE_PROFILE, 'create profile', 'create'),
      Choice(MenuState.SET_DEFAULT_PROFILE, 'set default profile', 'default'),
      Choice(MenuState.DELETE_PROFILE, 'delete profile', 'delete'),
    ]

    next_state = self._get_choice(choices)
    return next_state

  def _select_profile(self):
    """Select a profile."""
    index = self._get_choice(self._profiles_to_choices())
    self._set_profile(self.profiles.profiles[index])
    return MenuState.MODE_SELECT

  def _create_profile(self):
    """Create a new profile."""
    name = input('enter a name: ')

    profile_subdir = self._hash(name)
    profile_dir = os.path.join(self.manager_dir, profile_subdir)
    if os.path.exists(profile_dir):
      confirmed = self._confirm('that profile already exists. overwrite?')
      if not confirmed:
        print('profile was NOT created')
        return MenuState.PROFILE

      shutil.rmtree(profile_dir)

    selection_choices = [
        Choice(True, 'select from AppData', 'appdata'),
        Choice(False, 'manually enter directory', 'manual')
    ]
    use_appdata = self._get_choice(selection_choices)

    game_directory = ''
    while True:
      if use_appdata:
        settings_dirs = os.listdir(self.appdata_dir)
        choices = [Choice(i, d, d) for i, d in enumerate(settings_dirs)]
        index = self._get_choice(choices)
        game_directory = os.path.join(self.appdata_dir, settings_dirs[index])
      else:
        game_directory = input('absolute path to game directory: ')

      if os.path.isdir(game_directory):
        break

      print('selected option is not a directory')

    profile = Profile(name, game_directory)
    self.profiles.profiles.append(profile)
    os.mkdir(profile_dir)

    self._write_profiles_file()
    return MenuState.PROFILE

  def _set_default_profile(self):
    """Set the default profile."""
    choices = self._profiles_to_choices()
    choices[self.profiles.default].highlight = True
    index = self._get_choice(choices)
    self.profiles.default = index
    self._write_profiles_file()
    return MenuState.PROFILE

  def _delete_profile(self):
    """Delete a profile."""
    index = self._get_choice(self._profiles_to_choices())
    name = self.profiles.profiles[index].name
    prompt = 'are you sure you want to delete profile %d (%s)' % (index, name)
    confirmed = self._confirm(prompt)
    if not confirmed:
      print('profile NOT deleted')
      return MenuState.PROFILE

    profile_subdir = self._hash(name)
    profile_dir = os.path.join(self.manager_dir, profile_subdir)
    shutil.rmtree(profile_dir)

    if self.profiles.default == index:
      self.profiles.default = 0
    del self.profiles.profiles[index]
    self._write_profiles_file()
    return MenuState.PROFILE

  # Special handlers.
  @staticmethod
  def _help():
    """Print help text and return to the selection state."""
    print(HELP_TEXT)
    return MenuState.MODE_SELECT

  # Running helpers.
  def _mainloop(self):
    if self.profile:
      state = MenuState.MODE_SELECT
    else:
      state = MenuState.PROFILE

    handlers = {
      MenuState.MODE_SELECT: self._select,
      MenuState.CREATE: self._create,
      MenuState.LOAD: self._load,
      MenuState.AUTOLOAD: self._autoload,
      MenuState.REORDER: self._reorder,
      MenuState.DELETE: self._delete,
      MenuState.PROFILE: self._profile,
      MenuState.SELECT_PROFILE: self._select_profile,
      MenuState.CREATE_PROFILE: self._create_profile,
      MenuState.SET_DEFAULT_PROFILE: self._set_default_profile,
      MenuState.DELETE_PROFILE: self._delete_profile,
      MenuState.HELP: self._help,
    }

    while state != MenuState.EXIT:
      try:
        state = handlers[state]()
      except NoProfileException:
        print('no profiles')
        state = MenuState.PROFILE
      except NoSaveException:
        print('no saves')
        state = MenuState.MODE_SELECT

  def main(self):
    try:
      self._mainloop()
    except KeyboardInterrupt:
      print('exiting')
      sys.exit(0)


if __name__ == '__main__':
  manager = Manager()
  manager.main()