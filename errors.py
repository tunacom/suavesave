"""Error classes used by the save manager."""

__author__ = 'tunacom'


class ManagerError(Exception):
  """Base class for manager exceptions."""
  pass


class NoProfileException(ManagerError):
  """Exception to be raised if no profiles exist."""
  pass


class NoSaveException(ManagerError):
  """Exception to be raised if no saves exist."""
  pass
