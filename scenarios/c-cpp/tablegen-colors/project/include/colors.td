include "llvm/TableGen/SearchableTable.td"

class Color<string name, bits<32> value> {
  string Name = name;
  bits<32> Value = value;
}

def Red : Color<"red", 0xff0000>;
def Green : Color<"green", 0x00ff00>;
def Blue : Color<"blue", 0x0000ff>;

def Colors : GenericTable {
  let FilterClass = "Color";
  let CppTypeName = "Color";
  let Fields = ["Name", "Value"];
  let PrimaryKey = ["Value"];
  let PrimaryKeyName = "lookupColorByValue";
}

def lookupColor : SearchIndex {
  let Table = Colors;
  let Key = ["Name"];
}
