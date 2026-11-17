#!/usr/bin/env python3
"""Packs this folder into a .vsix, the file VS Code installs an extension from.

Usage: pack.py OUT.vsix   (then: code --install-extension OUT.vsix; `claude-speaks vscode
install` does both). A .vsix is a zip with the extension under extension/ and two small
descriptions of it, so no build tool is needed.
"""
import json
import os
import sys
import zipfile
from xml.sax.saxutils import escape, quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ("package.json", "extension.js")


def pack(out: str) -> str:
    with open(os.path.join(HERE, "package.json")) as f:
        package = json.load(f)
    manifest = f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id={quoteattr(package["name"])} Version={quoteattr(package["version"])} Publisher={quoteattr(package["publisher"])}/>
    <DisplayName>{escape(package["displayName"])}</DisplayName>
    <Description xml:space="preserve">{escape(package["description"])}</Description>
    <Categories>Other</Categories>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value={quoteattr(package["engines"]["vscode"])}/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value={quoteattr(",".join(package["extensionKind"]))}/>
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
  </Assets>
</PackageManifest>
"""
    types = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>
"""
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("extension.vsixmanifest", manifest)
        z.writestr("[Content_Types].xml", types)
        for name in FILES:
            z.write(os.path.join(HERE, name), f"extension/{name}")
    return f'{package["publisher"]}.{package["name"]}'


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(pack(sys.argv[1]))
