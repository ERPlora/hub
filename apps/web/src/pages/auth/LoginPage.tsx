// Autenticación con Ionic + Tailwind + react-icons. Pasos (ARQUITECTURA.md §2.9):
//   - 'pin'   : dispositivo de confianza → elegir usuario + PIN
//   - 'email' : login email+password (online)
//   - 'setup' : crear PIN tras el 1er login (con confirmación)
//
// Si el dispositivo es de confianza, se muestran TABS (PIN | Email) para alternar.
// El acceso por PIN solo se habilita si se marcó "Confiar en este dispositivo" al entrar
// con email (un icono "i" lo explica junto al checkbox).
import { useState } from 'react';
import { useHistory } from 'react-router-dom';
import {
  IonPage, IonContent, IonCard, IonCardContent, IonInput, IonButton, IonCheckbox,
  IonText, IonSpinner, IonSegment, IonSegmentButton, IonLabel, IonPopover,
} from '@ionic/react';
import { LuSun, LuMoon, LuLogIn, LuKeyRound, LuMail, LuInfo } from 'react-icons/lu';
import { Logo } from '../../ui/Logo';
import { PinPad } from '../../ui/PinPad';
import { useAuth } from '../../lib/auth';
import { useTheme } from '../../lib/theme';
import { useToast } from '../../lib/toast';

type Step = 'pin' | 'email' | 'setup';

export function LoginPage() {
  const auth = useAuth();
  const { dark, toggle } = useTheme();
  const [step, setStep] = useState<Step>(auth.trusted ? 'pin' : 'email');

  // Las tabs solo tienen sentido si el dispositivo es de confianza (hay PIN disponible)
  // y no estamos en el alta de PIN (setup).
  const showTabs = auth.trusted && step !== 'setup';

  return (
    <IonPage>
      <IonContent>
        <IonButton fill="clear" aria-label="Tema" className="absolute right-2 top-2 z-10" onClick={toggle}>
          {dark ? <LuSun size={20} /> : <LuMoon size={20} />}
        </IonButton>

        <div className="grid min-h-full place-items-center px-4 py-10">
          <div className="w-full max-w-[400px]">
            <div className="mb-8 flex flex-col items-center gap-3 text-center">
              <Logo size="lg" />
              <IonText color="medium">
                <p className="text-[14px]">
                  {step === 'setup' ? 'Crea tu PIN de acceso' : step === 'pin' ? 'Introduce tu PIN' : 'Inicia sesión en tu hub'}
                </p>
              </IonText>
            </div>

            <IonCard className="ion-no-margin">
              <IonCardContent>
                {showTabs && (
                  <IonSegment
                    value={step}
                    onIonChange={(e) => setStep(e.detail.value as Step)}
                    className="mb-5"
                  >
                    <IonSegmentButton value="pin">
                      <LuKeyRound size={16} className="mr-1.5" />
                      <IonLabel>PIN</IonLabel>
                    </IonSegmentButton>
                    <IonSegmentButton value="email">
                      <LuMail size={16} className="mr-1.5" />
                      <IonLabel>Email</IonLabel>
                    </IonSegmentButton>
                  </IonSegment>
                )}

                {step === 'pin' && <PinLogin onUseEmail={() => setStep('email')} hideSwitch={showTabs} />}
                {step === 'email' && <EmailForm onFirstTime={() => setStep('setup')} canUsePin={auth.trusted} onUsePin={() => setStep('pin')} hideSwitch={showTabs} />}
                {step === 'setup' && <PinSetup />}
              </IonCardContent>
            </IonCard>

            <p className="mt-6 text-center text-[12px] text-[color:var(--ion-color-medium)]">
              ERPlora · {step === 'pin' ? 'dispositivo de confianza' : 'conexión segura con Cloud'}
            </p>
          </div>
        </div>
      </IonContent>
    </IonPage>
  );
}

function EmailForm({ onFirstTime, canUsePin, onUsePin, hideSwitch }: { onFirstTime: () => void; canUsePin: boolean; onUsePin: () => void; hideSwitch?: boolean }) {
  const auth = useAuth();
  const { toast } = useToast();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [trust, setTrust] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const { firstTime } = await auth.loginEmail(email.trim().toLowerCase(), password, trust);
      if (firstTime && trust) onFirstTime(); // solo creamos PIN si el dispositivo es de confianza
      else toast('Sesión iniciada', { color: 'success' });
    } catch {
      setError('No se pudo iniciar sesión. Revisa tus credenciales o la conexión.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <IonInput label="Email" labelPlacement="stacked" type="email" autocomplete="username" fill="outline" placeholder="tu@empresa.com" value={email} onIonInput={(e) => setEmail(e.detail.value ?? '')} />
      <IonInput label="Contraseña" labelPlacement="stacked" type="password" autocomplete="current-password" fill="outline" placeholder="••••••••" value={password} onIonInput={(e) => setPassword(e.detail.value ?? '')} />

      <div className="flex items-center gap-1.5">
        <IonCheckbox checked={trust} onIonChange={(e) => setTrust(e.detail.checked)} labelPlacement="end">
          <span className="text-[13.5px]">Confiar en este dispositivo</span>
        </IonCheckbox>
        <IonButton id="trust-info" fill="clear" size="small" aria-label="Más información sobre dispositivos de confianza" className="m-0 h-6">
          <LuInfo size={16} />
        </IonButton>
        <IonPopover trigger="trust-info" triggerAction="click" side="top" alignment="center">
          <div className="max-w-[260px] p-3 text-[13px] leading-snug">
            <p className="mb-1 font-semibold">Acceso por PIN</p>
            <p className="text-[color:var(--ion-color-medium)]">
              Marca esta casilla para poder entrar con un <strong>PIN</strong> en este dispositivo
              la próxima vez, sin escribir email y contraseña. Si no la marcas, siempre tendrás que
              iniciar sesión con email.
            </p>
          </div>
        </IonPopover>
      </div>

      {error && <IonText color="danger"><p className="text-[13px]">{error}</p></IonText>}
      <IonButton type="submit" expand="block" disabled={loading}>
        {loading ? <IonSpinner name="crescent" /> : <><LuLogIn size={18} className="mr-2" />Entrar</>}
      </IonButton>
      {canUsePin && !hideSwitch && <IonButton fill="clear" size="small" onClick={onUsePin}>Usar PIN en su lugar</IonButton>}
    </form>
  );
}

function PinLogin({ onUseEmail, hideSwitch }: { onUseEmail: () => void; hideSwitch?: boolean }) {
  const auth = useAuth();
  const { toast } = useToast();
  const users = auth.trustedUsers;
  // Con un solo usuario no hace falta elegir; con varios se muestran las cards primero.
  const [userId, setUserId] = useState<string | null>(users.length === 1 ? users[0].id : null);
  const [pin, setPin] = useState('');
  const [error, setError] = useState(false);

  async function onChange(next: string) {
    setError(false);
    setPin(next);
    if (next.length === 4 && userId) {
      try {
        await auth.loginPin(userId, next);
        toast('Bienvenido', { color: 'success' });
      } catch {
        setError(true);
        setPin('');
      }
    }
  }

  const current = users.find((u) => u.id === userId);

  // Paso 1 — elegir con qué usuario autenticarse (cards de todos los disponibles).
  if (!current) {
    return (
      <div className="flex flex-col gap-4">
        <IonText color="medium"><p className="text-center text-[14px]">Elige tu usuario</p></IonText>
        <div className="grid grid-cols-2 gap-3">
          {users.map((u) => (
            <button
              key={u.id}
              type="button"
              onClick={() => { setUserId(u.id); setPin(''); setError(false); }}
              className="flex flex-col items-center gap-2 rounded-xl border border-[color:var(--ion-color-step-150,#dcdcdc)] bg-[color:var(--ion-card-background,#fff)] p-4 text-center shadow-sm transition hover:-translate-y-0.5 hover:border-[color:var(--ion-color-primary)] hover:shadow-md active:scale-[.98]"
            >
              <span className="grid h-12 w-12 place-items-center rounded-full text-[16px] font-semibold text-[color:var(--ion-color-primary)]" style={{ background: 'rgba(20,150,214,.12)' }}>{u.initials}</span>
              <span className="min-w-0 max-w-full truncate text-[14px] font-semibold">{u.name}</span>
              {u.email && <span className="min-w-0 max-w-full truncate text-[11px] text-[color:var(--ion-color-medium)]">{u.email}</span>}
            </button>
          ))}
        </div>
        {!hideSwitch && <IonButton fill="clear" size="small" onClick={onUseEmail}>Iniciar sesión con email</IonButton>}
      </div>
    );
  }

  // Paso 2 — PIN del usuario elegido.
  return (
    <div className="flex flex-col items-center gap-5">
      <div className="text-center">
        <span className="grid mx-auto h-14 w-14 place-items-center rounded-full text-[18px] font-semibold text-[color:var(--ion-color-primary)]" style={{ background: 'rgba(20,150,214,.12)' }}>{current.initials}</span>
        <p className="mt-2 text-[14px] font-semibold">{current.name}</p>
        {users.length > 1 && (
          <button
            type="button"
            onClick={() => { setUserId(null); setPin(''); setError(false); }}
            className="mt-1 text-[12px] text-[color:var(--ion-color-primary)] hover:underline"
          >
            Cambiar usuario
          </button>
        )}
      </div>
      <PinPad value={pin} onChange={onChange} error={error} />
      {error && <IonText color="danger"><p className="text-[13px]">PIN incorrecto</p></IonText>}
      {!hideSwitch && <IonButton fill="clear" size="small" onClick={onUseEmail}>Iniciar sesión con email</IonButton>}
    </div>
  );
}

function PinSetup() {
  const auth = useAuth();
  const history = useHistory();
  const { toast } = useToast();
  const [first, setFirst] = useState('');
  const [confirm, setConfirm] = useState('');
  const [phase, setPhase] = useState<'first' | 'confirm'>('first');
  const [error, setError] = useState(false);

  async function onChange(next: string) {
    setError(false);
    if (phase === 'first') {
      setFirst(next);
      if (next.length === 4) setPhase('confirm');
    } else {
      setConfirm(next);
      if (next.length === 4) {
        if (next === first) {
          await auth.setupPin(next);
          toast('PIN creado', { color: 'success' });
          history.push('/');
        } else {
          setError(true);
          setFirst('');
          setConfirm('');
          setPhase('first');
        }
      }
    }
  }

  return (
    <div className="flex flex-col items-center gap-5">
      <IonText color="medium"><p className="text-[14px]">{phase === 'first' ? 'Elige un PIN de 4 dígitos' : 'Confirma tu PIN'}</p></IonText>
      <PinPad value={phase === 'first' ? first : confirm} onChange={onChange} error={error} />
      {error && <IonText color="danger"><p className="text-[13px]">Los PIN no coinciden, inténtalo de nuevo</p></IonText>}
    </div>
  );
}
