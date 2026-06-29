import './App.css';
import CharacterConfigScreen from './screens/CharacterConfigScreen';
import CreateRoomScreen from './screens/CreateRoomScreen';
import JoinScreen from './screens/JoinScreen';
import { parseInviteToken, parseRoomCharactersRoomId } from './router';

/**
 * Top-level router. Reads the current path once at render:
 * - "/join/:token"            -> the invite join screen
 * - "/rooms/:roomId/characters" -> the host character-config screen
 * - anything else             -> the host create-room screen
 *
 * `pathname` is injectable so tests can render a specific route without touching
 * the global location.
 */
function App({ pathname = window.location.pathname }: { pathname?: string }) {
  const token = parseInviteToken(pathname);
  if (token !== null) {
    return <JoinScreen token={token} />;
  }
  const charactersRoomId = parseRoomCharactersRoomId(pathname);
  if (charactersRoomId !== null) {
    return <CharacterConfigScreen roomId={charactersRoomId} />;
  }
  return <CreateRoomScreen />;
}

export default App;
