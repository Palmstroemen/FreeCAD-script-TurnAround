# Tests for TurnAround.FCMacro. They need the FreeCAD GUI, so run them with:
#   QT_QPA_PLATFORM=offscreen freecad tests/turnaround_test.py
# The results are written to tests/turnaround_test.log; FreeCAD closes itself.

import math
import os
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

HERE = os.path.dirname(os.path.abspath(__file__))
MACRO = os.path.join(HERE, "..", "TurnAround.FCMacro")
LOG = os.path.join(HERE, "turnaround_test.log")
results = []


def runMacro():
	# a fresh namespace each time, so the macro must not rely on its globals surviving;
	# App, Gui and FreeCAD are preloaded like in FreeCAD's Python console
	namespace = {"__name__": "__main__", "App": App, "FreeCAD": App, "Gui": Gui, "FreeCADGui": Gui}
	with open(MACRO) as f:
		exec(compile(f.read(), MACRO, "exec"), namespace)
	wait(2000)


def wait(ms):
	loop = QtCore.QEventLoop()
	QtCore.QTimer.singleShot(ms, loop.quit)
	loop.exec_()


def visible(doc):
	return {o.Name for o in doc.Objects if o.ViewObject and o.ViewObject.Visibility}


def camera():
	return Gui.ActiveDocument.ActiveView.getCameraOrientation()


def turnedBy(before, after):
	return round(math.degrees((before.inverted() * after).Angle))


# camera orientations as FreeCAD's standard views set them
START_VIEWS = {
	"isometric": App.Rotation(0.424708, 0.17592, 0.339851, 0.820473),
	"front": App.Rotation(App.Vector(1, 0, 0), 90),
	"right": App.Rotation(0.5, 0.5, 0.5, 0.5),
	"top": App.Rotation(),
	"tilted": App.Rotation(App.Vector(1, 0, 0), 60).multiply(App.Rotation(App.Vector(0, 0, 1), 25)),
}
AXES = {"X": App.Vector(1, 0, 0), "Y": App.Vector(0, 1, 0), "Z": App.Vector(0, 0, 1)}


def mostVerticalAxis(cam):
	# the model axis that appears most vertical on the screen
	up = cam.multVec(App.Vector(0, 1, 0))
	return max(AXES, key=lambda name: abs(AXES[name].dot(up)))


def turnAxis(before, after):
	# the model axis closest to the axis the view has been turned around
	axis = after.multiply(before.inverted()).Axis
	return max(AXES, key=lambda name: abs(AXES[name].dot(axis)))


def makeDoc():
	doc = App.newDocument("T")
	part = doc.addObject("App::Part", "Part")
	body = doc.addObject("PartDesign::Body", "Body")
	part.addObject(body)
	box = doc.addObject("PartDesign::AdditiveBox", "Box")
	body.addObject(box)
	body2 = doc.addObject("PartDesign::Body", "Body001")
	binder = body2.newObject("PartDesign::ShapeBinder", "ShapeBinder")
	binder.Support = [(box, "")]
	doc.addObject("Part::Box", "Free")
	doc.recompute()
	Gui.Selection.clearSelection()
	# without a screen, the very first animated camera move of a new view does not run
	view = Gui.ActiveDocument.ActiveView
	view.setCameraOrientation(view.getCameraOrientation(), True)
	wait(300)
	return doc


def check(name, condition, detail=""):
	results.append("%s %s %s" % ("PASS" if condition else "FAIL", name, detail))


def test_face_selected():
	doc = makeDoc()
	before, camBefore = visible(doc), camera()
	Gui.Selection.addSelection(doc.Name, "Part", "Body.Box.Face1")
	runMacro()
	shown = visible(doc)
	check("face: selection and its containers stay", {"Part", "Body", "Box"} <= shown, sorted(shown))
	check("face: other objects hidden", not ({"Free", "Body001", "ShapeBinder"} & shown), sorted(shown))
	check("face: view turned by 180 degrees", turnedBy(camBefore, camera()) == 180, turnedBy(camBefore, camera()))
	check("face: no helper object in the document", doc.getObject("TurnAround") is None)
	runMacro()
	check("face: everything back after the second turn", visible(doc) == before, sorted(before ^ visible(doc)))
	check("face: view back after the second turn", turnedBy(camBefore, camera()) == 0, turnedBy(camBefore, camera()))
	App.closeDocument(doc.Name)


def test_container_selected():
	doc = makeDoc()
	Gui.Selection.addSelection(doc.Name, "Part", "Body.")
	runMacro()
	shown = visible(doc)
	check("body: its features stay", {"Part", "Body", "Box"} <= shown, sorted(shown))
	check("body: other objects hidden", "Free" not in shown, sorted(shown))
	runMacro()
	App.closeDocument(doc.Name)


def test_hidden_object_deleted():
	doc = makeDoc()
	before = visible(doc)
	Gui.Selection.addSelection(doc.Name, "Part", "Body.Box.Face1")
	runMacro()
	doc.removeObject("Free")
	try:
		runMacro()
		check("deleted: second turn works", True)
	except Exception:
		check("deleted: second turn works", False, traceback.format_exc())
	check("deleted: no helper object left", doc.getObject("TurnAround") is None)
	check("deleted: the rest is back", visible(doc) == before - {"Free"}, sorted((before - {"Free"}) ^ visible(doc)))
	App.closeDocument(doc.Name)


def test_selection_lost():
	doc = makeDoc()
	before = visible(doc)
	Gui.Selection.addSelection(doc.Name, "Part", "Body.Box.Face1")
	runMacro()
	Gui.Selection.clearSelection()
	runMacro()
	check("lost: everything back", visible(doc) == before, sorted(before ^ visible(doc)))
	App.closeDocument(doc.Name)


def test_no_selection():
	doc = makeDoc()
	before = visible(doc)
	runMacro()
	check("none: nothing hidden", visible(doc) == before, sorted(before ^ visible(doc)))
	runMacro()
	App.closeDocument(doc.Name)


def test_turn_axis():
	doc = makeDoc()
	view = Gui.ActiveDocument.ActiveView
	for name, start in START_VIEWS.items():
		# without a screen only an animated camera move arrives reliably
		view.setCameraOrientation(start, True)
		wait(1500)
		before = camera()
		runMacro()
		after = camera()
		check("axis %s: turned around the most vertical axis" % name,
			turnAxis(before, after) == mostVerticalAxis(before),
			"expected %s, turned around %s" % (mostVerticalAxis(before), turnAxis(before, after)))
	App.closeDocument(doc.Name)


try:
	for test in (test_turn_axis, test_face_selected, test_container_selected, test_hidden_object_deleted,
	             test_selection_lost, test_no_selection):
		try:
			test()
		except Exception:
			results.append("FAIL %s raised\n%s" % (test.__name__, traceback.format_exc()))
			for name in list(App.listDocuments()):
				App.closeDocument(name)
finally:
	with open(LOG, "w") as f:
		f.write("\n".join(results) + "\n")
	Gui.getMainWindow().close()
