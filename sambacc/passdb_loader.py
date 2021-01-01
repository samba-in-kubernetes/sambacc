def _samba_modules():
    from samba.samba3 import param
    from samba.samba3 import passdb

    return param, passdb


class PassDBLoader:
    def __init__(self, smbconf=None):
        param, passdb = _samba_modules()
        lp = param.get_context()
        if smbconf is None:
            lp.load_default()
        else:
            lp.load(smbconf)
        passdb.set_secrets_dir(lp.get("private dir"))
        self._pdb = passdb.PDB(lp.get("passdb backend"))
        self._passdb = passdb

    def add_user(self, user_entry):
        if not (user_entry.nt_passwd or user_entry.plaintext_passwd):
            raise ValueError(
                f"user entry {user_entry.username} lacks password value"
            )
        # probe for an existing user, by name
        try:
            samu = self._pdb.getsampwnam(user_entry.username)
        except self._passdb.error:
            samu = None
        # if it doesn't exist, create it
        if samu is None:
            # FIXME, research correct flag value
            self._pdb.create_user(user_entry.username, 0)
            samu = self._pdb.getsampwnam(user_entry.username)
        # update password/metadata
        if user_entry.nt_passwd:
            samu.nt_passwd = user_entry.nt_passwd
        elif user_entry.plaintext_passwd:
            samu.plaintext_passwd = user_entry.plaintext_passwd
        # update the db
        self._pdb.update_sam_account(samu)
