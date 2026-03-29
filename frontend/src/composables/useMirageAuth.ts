import { useAuth } from "@clerk/vue";

export const SIGN_IN_REQUIRED_MESSAGE = "You must sign in to continue.";

type TokenGetter = (() => Promise<string | null>) | null | undefined;

export async function getRequiredSessionToken(
  getToken: TokenGetter,
): Promise<string> {
  const token = await getToken?.();
  if (!token) {
    throw new Error(SIGN_IN_REQUIRED_MESSAGE);
  }
  return token;
}

export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  getToken: TokenGetter,
): Promise<Response> {
  const token = await getRequiredSessionToken(getToken);
  const headers = new Headers(init.headers ?? undefined);
  headers.set("Authorization", `Bearer ${token}`);

  return fetch(input, {
    ...init,
    headers,
  });
}

export function useMirageAuth() {
  const { getToken, isLoaded, isSignedIn, sessionId, userId } = useAuth();

  async function apiFetch(
    input: RequestInfo | URL,
    init: RequestInit = {},
  ): Promise<Response> {
    return authenticatedFetch(input, init, getToken.value);
  }

  return {
    apiFetch,
    getToken,
    isLoaded,
    isSignedIn,
    sessionId,
    userId,
  };
}
