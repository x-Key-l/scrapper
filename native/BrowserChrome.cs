using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace SceneTrace
{
    internal sealed class BrowserTabs : UserControl
    {
        private readonly FlowLayoutPanel strip = new FlowLayoutPanel {Dock=DockStyle.Fill,WrapContents=false,AutoScroll=true,Padding=new Padding(8,4,0,0)};
        private readonly Panel content = new Panel {Dock=DockStyle.Fill};
        private readonly Panel toolbar = new Panel {Dock=DockStyle.Top,Height=48};
        private readonly Dictionary<Panel,Button> buttons = new Dictionary<Panel,Button>();
        private Panel selected;
        internal event EventHandler SelectedIndexChanged;
        internal event Action<Panel> CloseRequested;
        internal event Action NewRequested;
        internal sealed class PageCollection : Collection<Panel>
        {
            private readonly BrowserTabs owner;
            internal PageCollection(BrowserTabs parent){owner=parent;}
            protected override void InsertItem(int index,Panel item){base.InsertItem(index,item);owner.Attach(item);}
            protected override void RemoveItem(int index){var item=this[index];base.RemoveItem(index);owner.Detach(item);}
        }
        internal PageCollection TabPages {get;}
        internal int TabCount => TabPages.Count;
        internal Panel SelectedTab
        {
            get=>selected;
            set
            {
                if(selected==value)return;
                if(selected!=null)selected.Visible=false;
                selected=value;
                foreach(var pair in buttons)pair.Value.BackColor=pair.Key==selected?Color.FromArgb(48,52,61):Color.FromArgb(27,30,36);
                if(selected!=null){selected.Visible=true;selected.BringToFront();}
                SelectedIndexChanged?.Invoke(this,EventArgs.Empty);
            }
        }
        internal BrowserTabs()
        {
            TabPages=new PageCollection(this);BackColor=Color.FromArgb(24,27,33);
            var row=new Panel{Dock=DockStyle.Top,Height=42,BackColor=BackColor};
            var add=new Button{Dock=DockStyle.Right,Width=42,Text="+",FlatStyle=FlatStyle.Flat,ForeColor=Color.White,AccessibleName="New browser tab"};add.FlatAppearance.BorderSize=0;add.Click+=(s,e)=>NewRequested?.Invoke();row.Controls.Add(strip);row.Controls.Add(add);
            Controls.Add(content);Controls.Add(toolbar);Controls.Add(row);
        }
        internal void SetToolbar(ToolStrip tools){tools.Dock=DockStyle.Fill;toolbar.Controls.Add(tools);}
        private void Attach(Panel page)
        {
            page.Dock=DockStyle.Fill;page.Visible=false;content.Controls.Add(page);
            var button=new Button{Text=page.Text,Width=205,Height=32,FlatStyle=FlatStyle.Flat,TextAlign=ContentAlignment.MiddleLeft,Padding=new Padding(10,0,20,0),Margin=new Padding(0,0,4,0),ForeColor=Color.FromArgb(224,229,239),BackColor=BackColor,AccessibleName=page.Text,AutoEllipsis=true};
            button.FlatAppearance.BorderSize=0;
            button.Click+=(s,e)=>SelectedTab=page;
            button.MouseDown+=(s,e)=>{if(e.Button==MouseButtons.Middle)CloseRequested?.Invoke(page);};
            var close=new Button{Text="×",Width=25,Dock=DockStyle.Right,FlatStyle=FlatStyle.Flat,ForeColor=Color.Silver,TabStop=false,AccessibleName="Close "+page.Text};close.FlatAppearance.BorderSize=0;close.Click+=(s,e)=>CloseRequested?.Invoke(page);button.Controls.Add(close);
            page.TextChanged+=(s,e)=>{button.Text=page.Text;button.AccessibleName=page.Text;};
            buttons[page]=button;strip.Controls.Add(button);
        }
        private void Detach(Panel page)
        {
            content.Controls.Remove(page);if(buttons.TryGetValue(page,out var button)){strip.Controls.Remove(button);button.Dispose();buttons.Remove(page);}
            if(selected==page){selected=null;SelectedTab=TabPages.Count>0?TabPages[0]:null;}
        }
    }
    internal sealed class RoundedAddress : ToolStripControlHost
    {
        private sealed class Field : Panel
        {
            internal readonly TextBox Input=new TextBox{BorderStyle=BorderStyle.None,Dock=DockStyle.Fill,BackColor=Color.FromArgb(36,40,49),ForeColor=Color.FromArgb(230,235,245)};
            internal Field(){BackColor=Color.FromArgb(36,40,49);Padding=new Padding(12,8,12,6);Controls.Add(Input);Resize+=(s,e)=>{using(var p=new GraphicsPath()){int d=18;p.AddArc(0,0,d,d,180,90);p.AddArc(Width-d,0,d,d,270,90);p.AddArc(Width-d,Height-d,d,d,0,90);p.AddArc(0,Height-d,d,d,90,90);p.CloseFigure();var previous=Region;Region=new Region(p);previous?.Dispose();}};}
        }
        private readonly Field field;
        internal RoundedAddress():base(new Field()){field=(Field)Control;Height=36;field.Input.KeyDown+=(s,e)=>OnKeyDown(e);}
        public override string Text {get=>field?.Input.Text??"";set{if(field!=null)field.Input.Text=value;}}
        public new void Focus()=>field.Input.Focus();
        internal void SelectAll()=>field.Input.SelectAll();
    }
    internal sealed class ChromeColors : ProfessionalColorTable
    {
        public override Color ToolStripDropDownBackground=>Color.FromArgb(31,35,43);
        public override Color ImageMarginGradientBegin=>ToolStripDropDownBackground;
        public override Color ImageMarginGradientMiddle=>ToolStripDropDownBackground;
        public override Color ImageMarginGradientEnd=>ToolStripDropDownBackground;
        public override Color MenuItemSelected=>Color.FromArgb(53,61,77);
        public override Color MenuItemBorder=>Color.FromArgb(70,80,100);
        public override Color ToolStripBorder=>Color.FromArgb(31,35,43);
        public override Color ButtonSelectedGradientBegin=>MenuItemSelected;
        public override Color ButtonSelectedGradientMiddle=>MenuItemSelected;
        public override Color ButtonSelectedGradientEnd=>MenuItemSelected;
    }
}
