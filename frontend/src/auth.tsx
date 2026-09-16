import { createContext, useContext, type Dispatch, type SetStateAction } from 'react';
import type { Auth } from './api/types';

export const AuthContext = createContext<{
  auth: Auth | null | undefined;
  setAuth: Dispatch<SetStateAction<Auth | null | undefined>>;
}>({ auth: undefined, setAuth: () => {} });
export const useAuth = () => useContext(AuthContext);
