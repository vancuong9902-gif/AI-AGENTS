import { createContext } from 'react';

const noop = () => {};

export const defaultAuthContextValue = {
  user: null,
  token: null,
  role: null,
  userId: null,
  login: noop,
  logout: noop,
};

export const AuthContext = createContext(defaultAuthContextValue);
