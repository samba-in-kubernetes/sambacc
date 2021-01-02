import os


class LineFileLoader:
    def __init__(self, path):
        self.path = path
        self.lines = []

    def read(self):
        with open(self.path) as f:
            self.readfp(f)

    def write(self):
        tpath = self._tmp_path(self.path)
        with open(tpath, "w") as f:
            self.writefp(f)
        os.rename(tpath, self.path)

    def _tmp_path(self, path):
        # for later: make this smarter
        return f"{path}.tmp"

    def readfp(self, fp):
        for line in fp.readlines():
            self.lines.append(line)

    def writefp(self, fp):
        prev = None
        for line in self.lines:
            if prev and not prev.endswith("\n"):
                fp.write("\n")
            fp.write(line)
            prev = line
        fp.flush()


class PasswdFileLoader(LineFileLoader):
    def __init__(self, path="/etc/passwd"):
        super().__init__(path)
        self._usernames = set()

    def readfp(self, fp):
        super().readfp(fp)
        self._update_usernames_cache()

    def _update_usernames_cache(self):
        for line in self.lines:
            if ":" in line:
                u = line.split(":")[0]
                self._usernames.add(u)

    def add_user(self, user_entry):
        if user_entry.username in self._usernames:
            return
        line = "{}\n".format(":".join(user_entry.passwd_fields()))
        self.lines.append(line)
        self._usernames.add(user_entry.username)


class GroupFileLoader(LineFileLoader):
    def __init__(self, path="/etc/group"):
        super().__init__(path)
        self._groupnames = set()

    def readfp(self, fp):
        super().readfp(fp)
        self._update_groupnames_cache()

    def _update_groupnames_cache(self):
        for line in self.lines:
            if ":" in line:
                u = line.split(":")[0]
                self._groupnames.add(u)

    def add_group(self, group_entry):
        if group_entry.groupname in self._groupnames:
            return
        line = "{}\n".format(":".join(group_entry.group_fields()))
        self.lines.append(line)
        self._groupnames.add(group_entry.groupname)
