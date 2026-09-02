-- A module that declares NO capability has nothing to be granted: it must read 1, always. This is
-- the positive control that `:capabilities_granted` is answered per CALLING MODULE and is not one
-- flag for the whole hub.
SELECT :capabilities_granted AS can_sign;
