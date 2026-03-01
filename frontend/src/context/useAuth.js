import { useContext } from 'react';
import { AuthContext } from './authContextBase';

export function useAuth() {
  return useContext(AuthContext);
}
