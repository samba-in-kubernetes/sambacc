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
        for line in self.lines:
            fp.write(line)
        fp.flush()


class PasswdFileLoader(LineFileLoader):
    def __init__(self, path="/etc/passwd"):
        super().__init__(path)

    def add_user(self, user_entry):
        line = "{}\n".format(":".join(user_entry.passwd_fields()))
        self.lines.apppend(line)


class GroupFileLoader(LineFileLoader):
    def __init__(self, path="/etc/group"):
        super().__init__(path)

    def add_group(self, group_entry):
        line = "{}\n".format(":".join(group_entry.group_fields()))
        self.lines.apppend(line)
